import streamlit as st
import pandas as pd

try:
    col = st.column_config.NumberColumn("Test", alignment="center")
    print("Success: alignment exists")
except TypeError as e:
    print(f"Error: {e}")

# Check all available arguments
import inspect
print(f"Args: {inspect.signature(st.column_config.NumberColumn).parameters.keys()}")
