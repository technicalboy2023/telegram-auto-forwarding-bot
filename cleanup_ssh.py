import paramiko
import sys
import time

def clean_server():
    hostname = 'ssh-amna.alwaysdata.net'
    username = 'amna'
    password = 'Aman@4899'

    print(f"Connecting to {hostname}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(hostname, username=username, password=password, timeout=10)
        print("✅ SSH Connection successful!")

        # Commands to wipe the server
        commands = [
            "echo 'Cleaning up server...'",
            "pkill -9 -u amna python || true",
            "pkill -9 -u amna python3 || true",
            "pkill -9 -f bot.py || true",
            "rm -rf ~/www/*",
            "rm -rf ~/www/.* 2>/dev/null || true",
            "rm -rf ~/.cache/pip",
            "rm -rf ~/.local",
            "rm -rf ~/admin",
            "echo 'RAM and Storage cleaned!'",
            "ps -u amna -o pid,comm,%mem,%cpu",
            "df -h ~",
            "free -m || true"
        ]

        for cmd in commands:
            print(f"Executing: {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd)
            time.sleep(0.5)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            if out:
                print(f"Output:\n{out}")
            if err:
                print(f"Error:\n{err}")
                
        print("✅ Server wipe complete!")

    except Exception as e:
        print(f"❌ Failed to connect or execute: {e}")
    finally:
        client.close()

if __name__ == '__main__':
    clean_server()
