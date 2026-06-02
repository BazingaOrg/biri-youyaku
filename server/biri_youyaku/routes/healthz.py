from importlib.metadata import PackageNotFoundError, version as _pkg_version

from fastapi import APIRouter

router = APIRouter()


def _get_version() -> str:
    """读取已安装包的版本号；本地未安装时回退到 pyproject 中的硬编码字符串。"""
    try:
        return _pkg_version("biri-youyaku-server")
    except PackageNotFoundError:
        return "0.0.0+local"


@router.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


@router.get("/v1/version")
async def get_version() -> dict[str, str]:
    """返回后端版本号，便于用户报 bug 时一眼贴出。"""
    return {"version": _get_version()}
