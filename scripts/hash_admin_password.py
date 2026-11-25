"""Generate a salted administrator password hash from a terminal."""

import sys
import warnings
from getpass import GetPassWarning, getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

from app.auth import hash_admin_password


def main():
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("管理员密码（12–64 个字符）：")
            confirmation = getpass("再次输入管理员密码：")
    except (GetPassWarning, EOFError):
        raise SystemExit("请在支持隐藏输入的交互式终端运行") from None
    if password != confirmation:
        raise SystemExit("两次输入的密码不一致")
    try:
        print(hash_admin_password(password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
