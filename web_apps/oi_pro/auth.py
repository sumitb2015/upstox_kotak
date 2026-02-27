import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
import jwt
from peewee import SqliteDatabase, Model, CharField, BooleanField, DateTimeField

# ── Configuration ──
SECRET_KEY = os.getenv("OIPRO_SECRET_KEY", "oipro-dev-secret-key-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

# ── Database Setup ──
db_path = os.path.join(os.path.dirname(__file__), "users.db")
db = SqliteDatabase(db_path)

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    email = CharField(unique=True)
    hashed_password = CharField()
    role = CharField(default="user")  # 'admin' or 'user'
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)

def init_db():
    db.connect()
    db.create_tables([User], safe=True)
    
    # Create default admin if no users exist
    if User.select().count() == 0:
        create_user("admin@oipro.com", "OIPro@123", role="admin")
    db.close()

# ── Auth Utilities ──
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user(email: str):
    try:
        return User.get(User.email == email)
    except User.DoesNotExist:
        return None

def create_user(email, password, role="user"):
    return User.create(
        email=email,
        hashed_password=get_password_hash(password),
        role=role
    )

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = get_user(email=email)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

async def check_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges"
        )
    return current_user

# ── Routes ──
@router.post("/api/login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user(form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": {"email": user.email, "role": user.role}}

@router.get("/api/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return {"email": current_user.email, "role": current_user.role}

@router.get("/api/users")
async def list_users(admin: User = Depends(check_admin)):
    users = User.select().dicts()
    return [{"email": u["email"], "role": u["role"], "is_active": u["is_active"], "created_at": u["created_at"]} for u in users]

@router.post("/api/users")
async def admin_create_user(user_data: dict, admin: User = Depends(check_admin)):
    email = user_data.get("email")
    password = user_data.get("password")
    role = user_data.get("role", "user")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
        
    if get_user(email):
        raise HTTPException(status_code=400, detail="User already exists")
        
    user = create_user(email, password, role)
    return {"email": user.email, "role": user.role, "status": "created"}

@router.delete("/api/users/{email}")
async def admin_delete_user(email: str, admin: User = Depends(check_admin)):
    if email == admin.email:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
        
    user = get_user(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.delete_instance()
    return {"status": "deleted", "email": email}
