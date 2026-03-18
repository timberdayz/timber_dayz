"""Reset admin passwords with correct bcrypt hashes."""
import asyncio
import asyncpg
import bcrypt


async def reset():
    conn = await asyncpg.connect(
        'postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp'
    )

    passwords = {
        'admin': 'Admin@123456',
        'xihong': 'Xihong@2025',
    }

    for username, password in passwords.items():
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

        # Verify hash is valid before writing
        assert bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8')), "Hash verification failed"

        await conn.execute(
            """
            UPDATE core.dim_users
            SET password_hash = $1,
                failed_login_attempts = 0,
                locked_until = NULL
            WHERE username = $2
            """,
            hashed, username
        )
        print(f"[OK] Reset password for {username}: {password}")
        print(f"     Hash: {hashed[:30]}...")

    await conn.close()
    print("\n[OK] All passwords reset successfully")


if __name__ == '__main__':
    asyncio.run(reset())
