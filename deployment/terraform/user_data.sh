#!/bin/bash

# Update system
apt-get update
apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker ubuntu

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install Git
apt-get install -y git

# Clone repository (replace with actual repository URL)
# git clone https://github.com/your-username/kr-sentiment-agent.git /opt/kr-sentiment-agent

# Create application directory
mkdir -p /opt/kr-sentiment-agent
cd /opt/kr-sentiment-agent

# Copy application files (this would be done via deployment pipeline)
# For now, we'll create a placeholder
echo "Application files will be deployed here" > README.txt

# Start services with Docker Compose
# docker-compose -f ${docker_compose_file} up -d

# Enable Docker service
systemctl enable docker
systemctl start docker

# Create systemd service for the application
cat > /etc/systemd/system/kr-sentiment-agent.service << EOF
[Unit]
Description=KR Sentiment Agent
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/kr-sentiment-agent
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
systemctl enable kr-sentiment-agent.service
systemctl start kr-sentiment-agent.service

