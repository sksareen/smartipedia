"""OAuth authentication routes — GitHub and Google login."""

import uuid

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# ---- Session helper ----
_signer = URLSafeTimedSerializer(settings.session_secret)
SESSION_COOKIE = "sp_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def set_session_cookie(response, user_id: str):
    token = _signer.dumps({"uid": user_id})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.base_url.startswith("https"),
    )


def clear_session_cookie(response):
    response.delete_cookie(SESSION_COOKIE)


def get_user_id_from_cookie(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = _signer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("uid")
    except Exception:
        return None


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    uid = get_user_id_from_cookie(request)
    if not uid:
        return None
    try:
        result = await db.execute(select(User).where(User.id == uuid.UUID(uid)))
        return result.scalar_one_or_none()
    except Exception:
        return None


# ---- OAuth setup ----
oauth = OAuth()

if settings.github_client_id:
    oauth.register(
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )

if settings.google_client_id:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


# ---- Routes ----

@router.get("/login/{provider}")
async def login(provider: str, request: Request):
    """Redirect to OAuth provider."""
    if provider not in ("github", "google"):
        return RedirectResponse("/")
    client = getattr(oauth, provider, None)
    if not client:
        return RedirectResponse("/?error=OAuth+provider+not+configured")
    redirect_uri = f"{settings.base_url}/auth/callback/{provider}"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/callback/{provider}")
async def callback(provider: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Handle OAuth callback — create/find user, set session cookie."""
    if provider not in ("github", "google"):
        return RedirectResponse("/")
    client = getattr(oauth, provider, None)
    if not client:
        return RedirectResponse("/")

    try:
        token = await client.authorize_access_token(request)
    except Exception as e:
        print(f"OAuth error: {e}")
        return RedirectResponse("/?error=OAuth+failed")

    # Get user info from provider
    if provider == "github":
        resp = await client.get("user", token=token)
        profile = resp.json()
        provider_id = str(profile["id"])
        name = profile.get("name") or profile.get("login", "")
        email = profile.get("email", "")
        avatar_url = profile.get("avatar_url", "")
        # GitHub may not return email in profile, fetch from /user/emails
        if not email:
            try:
                emails_resp = await client.get("user/emails", token=token)
                emails = emails_resp.json()
                primary = next((e for e in emails if e.get("primary")), None)
                if primary:
                    email = primary["email"]
            except Exception:
                pass
    elif provider == "google":
        userinfo = token.get("userinfo", {})
        provider_id = userinfo.get("sub", "")
        name = userinfo.get("name", "")
        email = userinfo.get("email", "")
        avatar_url = userinfo.get("picture", "")
    else:
        return RedirectResponse("/")

    # Upsert user
    result = await db.execute(
        select(User).where(User.provider == provider, User.provider_id == provider_id)
    )
    user = result.scalar_one_or_none()

    if user:
        # Update profile info
        user.name = name
        user.email = email
        user.avatar_url = avatar_url
    else:
        user = User(
            provider=provider,
            provider_id=provider_id,
            name=name,
            email=email,
            avatar_url=avatar_url,
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    # Set session cookie and redirect
    response = RedirectResponse("/", status_code=303)
    set_session_cookie(response, str(user.id))
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    clear_session_cookie(response)
    return response


# ---- Journey sync API ----

@router.get("/me")
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    """Get current user info (for JS to check login state)."""
    user = await get_current_user(request, db)
    if not user:
        return {"logged_in": False}
    return {
        "logged_in": True,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "provider": user.provider,
    }


@router.get("/journeys")
async def get_journeys(request: Request, db: AsyncSession = Depends(get_db)):
    """Get saved journeys for the current user."""
    user = await get_current_user(request, db)
    if not user:
        return {"journeys": []}
    return {"journeys": user.journeys or []}


@router.post("/journeys")
async def save_journeys(request: Request, db: AsyncSession = Depends(get_db)):
    """Save journeys for the current user (full replace from localStorage)."""
    user = await get_current_user(request, db)
    if not user:
        return {"error": "Not logged in"}, 401
    body = await request.json()
    user.journeys = body.get("journeys", [])
    await db.commit()
    return {"ok": True}
