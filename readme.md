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
        "sshd": {"disable_root": False}
      }
run_cmd:
  - wget -qO /root/provizzen.py https://raw.githubusercontent.com/derrekbertrand/provizzen/dev/provizzen.py
  - python /root/provizzen.py
```
