# 404Bot v2 - VPS Setup Guide

This guide provides instructions for setting up 404Bot v2 on a VPS with a single command.

## One-Command Installation

To install 404Bot v2 on your VPS with a single command, SSH into your VPS and run:

```bash
# Clone the repository
git clone https://github.com/yourusername/404botv2.git
cd 404botv2

# Make the installation script executable
chmod +x install.sh

# Run the installation script with sudo
sudo ./install.sh
```

## What the Installation Script Does

The `install.sh` script automates the entire setup process:

1. **System Updates**: Updates all system packages
2. **Dependencies**: Installs Python, pip, git, and other required system dependencies
3. **Virtual Environment**: Creates a Python virtual environment for isolated dependencies
4. **Python Packages**: Installs all required Python packages from requirements.txt
5. **Logging Setup**: Creates and configures the logs directory
6. **Environment Configuration**: Sets up the .env file from the template
7. **Systemd Service**: Creates a systemd service for auto-starting the bot
8. **Log Rotation**: Configures log rotation to prevent disk space issues
9. **Monitoring Script**: Creates a script for easy monitoring of the bot

## Post-Installation Steps

After running the installation script:

1. **Configure Environment Variables**:
   ```bash
   nano /path/to/404botv2/.env
   ```
   
   Fill in your:
   - Ethereum node URLs
   - Private key and wallet address
   - Contract addresses
   - DEX router addresses
   - Trading parameters

2. **Start the Bot**:
   ```bash
   sudo systemctl start 404botv2.service
   ```

3. **Check Status**:
   ```bash
   sudo systemctl status 404botv2.service
   ```

4. **Monitor the Bot**:
   ```bash
   ./monitor.sh
   ```

## Useful Commands

- **Start the bot**:
  ```bash
  sudo systemctl start 404botv2.service
  ```

- **Stop the bot**:
  ```bash
  sudo systemctl stop 404botv2.service
  ```

- **Restart the bot**:
  ```bash
  sudo systemctl restart 404botv2.service
  ```

- **View logs in real-time**:
  ```bash
  tail -f logs/bot404.log
  ```

- **View recent trades**:
  ```bash
  tail -f logs/trades.log
  ```

- **View performance metrics**:
  ```bash
  tail -f logs/performance.log
  ```

## Security Recommendations

1. **Dedicated VPS**: Use a dedicated VPS for running the bot
2. **Firewall**: Configure a firewall to only allow necessary connections
3. **SSH Key Authentication**: Disable password authentication and use SSH keys
4. **Regular Updates**: Keep the system and bot updated
5. **Secure .env File**: Restrict permissions on the .env file:
   ```bash
   chmod 600 .env
   ```

## Troubleshooting

If you encounter issues:

1. **Check Logs**:
   ```bash
   tail -f logs/bot404.log
   ```

2. **Verify Configuration**:
   Ensure all values in the .env file are correctly set

3. **Restart Service**:
   ```bash
   sudo systemctl restart 404botv2.service
   ```

4. **Check System Resources**:
   ```bash
   top
   df -h
   ```

5. **Verify Node Connection**:
   Ensure your Ethereum node is accessible and responding
