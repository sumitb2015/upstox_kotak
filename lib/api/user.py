import upstox_client
from upstox_client.rest import ApiException

def get_user_profile(access_token):
    """
    Retrieve details like user name, email, and brokerage type.
    
    Args:
        access_token (str): The access token obtained from Token API
        
    Returns:
        dict: User profile details
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.UserApi(upstox_client.ApiClient(configuration))
    
    try:
        api_response = api_instance.get_profile("2.0")
        return api_response.data
    except ApiException as e:
        print(f"Exception when calling UserApi->get_profile: {e}")
        return None

def get_funds_summary(access_token):
    """
    Returns equity and commodity margin/fund details.
    
    Args:
        access_token (str): The access token obtained from Token API
        
    Returns:
        dict: Funds and margin details
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.UserApi(upstox_client.ApiClient(configuration))
    
    try:
        api_response = api_instance.get_user_fund_margin("2.0")
        return api_response.data
    except ApiException as e:
        print(f"Exception when calling UserApi->get_user_fund_margin: {e}")
        return None

def logout(access_token):
    """
    Logout the current user session and invalidate the access token.
    
    Args:
        access_token (str): The access token to invalidate
        
    Returns:
        bool: True if logout successful, False otherwise
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.LoginApi(upstox_client.ApiClient(configuration))
    
    try:
        api_response = api_instance.logout("2.0")
        print("✅ Logout successful")
        return True
    except ApiException as e:
        print(f"Exception when calling LoginApi->logout: {e}")
        return False
