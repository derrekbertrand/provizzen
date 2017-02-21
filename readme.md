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
        "nginx": {
          "fpm_sites": [
            {
              "user": "webuser",
              "socket": "127.0.0.1:9001",
              "hostname": "default_server"
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
          },
          {
            "name": "webuser",
            "pass": "5EcRe7squ3Rr1L2",
            "groups": ["nginx"],
            "authorized_keys": ["ssh-rsa PASTE YOUR KEYS HERE"]
          }
        ]
      }
runcmd:
  - wget -qO - https://github.com/derrekbertrand/provizzen/archive/dev.tar.gz | tar xzf -
  - mv /root/config.json /root/provizzen-dev/config.json
  - python /root/provizzen-dev/provizzen.py
```
