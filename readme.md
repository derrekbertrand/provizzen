# Provizzen

A python module designed to provision a server using shell scripting.

## Usage

The following will download the script into a DO droplet and run it. You can perform these steps your self to the same effect.

```yaml
#cloud-config
write_files:
  - path: /root/config.json
    content: |
      {
        "mariadb": {
          "accounts": [
            {
              "username": "myuser",
              "password": "wordpass1",
              "database": "mydatabase"
            }
          ]
        },
        "sshd": {"disable_root": false},
        "users": [
          {
            "name": "someuser",
            "pass": "5EcRe7squ3Rr1L",
            "groups": ["wheel"],
            "authorized_keys": ["ssh-rsa PASTE YOUR KEYS HERE"]
          }
        ]
      }
run_cmd:
  - wget -qO /root/provizzen.py https://raw.githubusercontent.com/derrekbertrand/provizzen/dev/provizzen.py
  - python /root/provizzen.py
```
