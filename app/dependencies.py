# app/dependencies.py

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

# Mock database or user retrieval for the sake of demonstration
from app.models import MongoUser  # Update with your actual user model import

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Secret key for JWT decoding
SECRET_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.cThIIoDvwdueQB468K5xDc5633seEFoqwxjF_xSJyQQ"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

async def get_current_user_id(token: str = Depends(oauth2_scheme)):
    """
    Retrieves the user ID from the provided OAuth2 token.
    This function can be modified to match your project's authentication strategy.
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode the JWT token to extract the user ID
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")  # "sub" is a common field for user identifiers in JWT
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Fetch user from database (optional: validate if user exists)
    user = await MongoUser.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Return the user ID
    return str(user.id)
