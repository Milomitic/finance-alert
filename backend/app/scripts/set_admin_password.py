"""Generate a bcrypt hash to paste into ADMIN_PASSWORD_HASH."""
import getpass
import bcrypt


def main() -> None:
    pw = getpass.getpass("New admin password: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw != pw2:
        raise SystemExit("Passwords do not match")
    if len(pw) < 8:
        raise SystemExit("Password must be at least 8 characters")
    hashed = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    print("\nPaste this into your .env as ADMIN_PASSWORD_HASH:\n")
    print(hashed)


if __name__ == "__main__":
    main()
