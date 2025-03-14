#!/bin/bash
# 404Bot v2 - One-Command VPS Installation Script
# This script installs all dependencies, sets up logging, and configures the bot

set -e  # Exit on any error

# Text colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Print banner
echo -e "${BLUE}"
echo "  _  _    ___  _  _    ___         _           ___  "
echo " | || |  / _ \| || |  | _ ) ___ __| |_ __ __ _|_  ) "
echo " | __ | | (_) | __ |  | _ \/ _ (_-<  _/ _/ _\` |/ /  "
echo " |_||_|  \___/|_||_|  |___/\___/__/\__\__\__, /___|"
echo "                                         |___/      "
echo -e "${NC}"
echo -e "${YELLOW}One-Command VPS Installation Script${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root (use sudo)${NC}"
  exit 1
fi

# Get installation directory
INSTALL_DIR=$(pwd)
echo -e "${GREEN}Installing 404Bot v2 in:${NC} $INSTALL_DIR"
echo ""

# Update system
echo -e "${BLUE}[1/9]${NC} Updating system packages..."
apt-get update
apt-get upgrade -y

# Install dependencies
echo -e "${BLUE}[2/9]${NC} Installing system dependencies..."
apt-get install -y python3 python3-pip python3-venv git build-essential libssl-dev

# Create virtual environment
echo -e "${BLUE}[3/9]${NC} Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo -e "${BLUE}[4/9]${NC} Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create logs directory
echo -e "${BLUE}[5/9]${NC} Setting up logging directories..."
mkdir -p logs
chmod 755 logs

# Setup environment file
echo -e "${BLUE}[6/9]${NC} Setting up environment configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}Please edit the .env file with your configuration:${NC}"
    echo -e "${YELLOW}nano $INSTALL_DIR/.env${NC}"
else
    echo -e "${GREEN}Environment file already exists.${NC}"
fi

# Create systemd service for auto-start
echo -e "${BLUE}[7/9]${NC} Creating systemd service for auto-start..."
SERVICE_FILE="/etc/systemd/system/404botv2.service"

cat > $SERVICE_FILE << EOL
[Unit]
Description=404Bot v2 - MEV and Flash Loan Arbitrage Bot
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/main.py
Restart=on-failure
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=404botv2

[Install]
WantedBy=multi-user.target
EOL

# Reload systemd
systemctl daemon-reload
systemctl enable 404botv2.service

# Set up log rotation
echo -e "${BLUE}[8/9]${NC} Setting up log rotation..."
LOG_ROTATION_FILE="/etc/logrotate.d/404botv2"

cat > $LOG_ROTATION_FILE << EOL
$INSTALL_DIR/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 $(whoami) $(whoami)
    sharedscripts
    postrotate
        systemctl restart 404botv2.service
    endscript
}
EOL

chmod 644 $LOG_ROTATION_FILE

# Create monitoring script
echo -e "${BLUE}[9/9]${NC} Creating monitoring script..."
MONITOR_SCRIPT="$INSTALL_DIR/monitor.sh"

cat > $MONITOR_SCRIPT << EOL
#!/bin/bash
# 404Bot v2 - Monitoring Script

echo "===== 404Bot v2 Status ====="
systemctl status 404botv2.service

echo ""
echo "===== Recent Logs ====="
tail -n 50 $INSTALL_DIR/logs/bot404.log

echo ""
echo "===== Recent Trades ====="
tail -n 20 $INSTALL_DIR/logs/trades.log

echo ""
echo "===== Performance ====="
tail -n 10 $INSTALL_DIR/logs/performance.log

echo ""
echo "===== System Resources ====="
echo "CPU Usage:"
top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - \$1"%"}'

echo ""
echo "Memory Usage:"
free -h

echo ""
echo "Disk Usage:"
df -h | grep -v tmpfs
EOL

chmod +x $MONITOR_SCRIPT

# Final instructions
echo ""
echo -e "${GREEN}Installation Complete!${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Edit your configuration: nano $INSTALL_DIR/.env"
echo "2. Start the bot: systemctl start 404botv2.service"
echo "3. Monitor the bot: $INSTALL_DIR/monitor.sh"
echo ""
echo -e "${YELLOW}Useful Commands:${NC}"
echo "- Start bot: systemctl start 404botv2.service"
echo "- Stop bot: systemctl stop 404botv2.service"
echo "- Restart bot: systemctl restart 404botv2.service"
echo "- View logs: tail -f $INSTALL_DIR/logs/bot404.log"
echo "- Monitor bot: $INSTALL_DIR/monitor.sh"
echo ""
echo -e "${GREEN}Thank you for using 404Bot v2!${NC}"
