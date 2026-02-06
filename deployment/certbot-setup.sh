#!/bin/bash
# ========================================
# Let's Encrypt SSL Certificate Setup
# For Multi-Tenant JLPT (mikan.uz)
# ========================================
# This script automates SSL certificate acquisition using Certbot
# Supports both HTTP-01 challenge (api.mikan.uz) and DNS-01 challenge (*.mikan.uz wildcard)
# ========================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ========================================
# Configuration
# ========================================
DOMAIN="mikan.uz"
API_DOMAIN="api.mikan.uz"
WILDCARD_DOMAIN="*.mikan.uz"
EMAIL="${CERTBOT_EMAIL:-admin@mikan.uz}"
WEBROOT="/var/www/html"
CERT_PATH="/etc/letsencrypt/live"

# ========================================
# Prerequisites Check
# ========================================
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then 
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi

    # Check if Certbot is installed
    if ! command -v certbot &> /dev/null; then
        log_warn "Certbot not found. Installing..."
        
        # Detect OS and install Certbot
        if [ -f /etc/debian_version ]; then
            # Debian/Ubuntu
            apt-get update
            apt-get install -y certbot python3-certbot-nginx
        elif [ -f /etc/redhat-release ]; then
            # CentOS/RHEL
            yum install -y certbot python3-certbot-nginx
        else
            log_error "Unsupported OS. Please install Certbot manually."
            exit 1
        fi
        
        log_info "Certbot installed successfully"
    else
        log_info "Certbot is already installed ($(certbot --version))"
    fi

    # Check if Nginx is installed
    if ! command -v nginx &> /dev/null; then
        log_error "Nginx not found. Please install Nginx first."
        exit 1
    fi

    # Check if Nginx is running
    if ! systemctl is-active --quiet nginx; then
        log_warn "Nginx is not running. Starting Nginx..."
        systemctl start nginx
    fi

    # Create webroot directory for ACME challenge
    mkdir -p "$WEBROOT"
    
    log_info "Prerequisites check passed"
}

# ========================================
# Step 1: Obtain Certificate for api.mikan.uz (HTTP-01 Challenge)
# ========================================
setup_api_cert() {
    log_info "Setting up SSL certificate for $API_DOMAIN..."

    if [ -d "$CERT_PATH/$API_DOMAIN" ]; then
        log_warn "Certificate for $API_DOMAIN already exists. Skipping..."
        return 0
    fi

    # Use HTTP-01 challenge (requires port 80 accessible)
    certbot certonly \
        --webroot \
        --webroot-path="$WEBROOT" \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --force-renewal \
        -d "$API_DOMAIN" || {
            log_error "Failed to obtain certificate for $API_DOMAIN"
            return 1
        }

    log_info "Certificate for $API_DOMAIN obtained successfully"
}

# ========================================
# Step 2: Obtain Wildcard Certificate for *.mikan.uz (DNS-01 Challenge)
# ========================================
setup_wildcard_cert() {
    log_info "Setting up wildcard SSL certificate for $WILDCARD_DOMAIN..."

    # Check if DNS plugin is available
    if [ -z "$DNS_PLUGIN" ]; then
        log_warn "DNS_PLUGIN environment variable not set."
        log_warn "Wildcard certificates require DNS-01 challenge."
        log_warn "You need a DNS plugin for your provider (e.g., cloudflare, route53, digitalocean)."
        log_warn ""
        log_warn "Example setup for Cloudflare:"
        log_warn "  1. Install plugin: apt-get install python3-certbot-dns-cloudflare"
        log_warn "  2. Create credentials file: /root/.secrets/cloudflare.ini"
        log_warn "  3. Set environment variable: export DNS_PLUGIN=cloudflare"
        log_warn "  4. Re-run this script"
        log_warn ""
        log_warn "Skipping wildcard certificate setup..."
        return 1
    fi

    if [ -d "$CERT_PATH/$API_DOMAIN" ] && [ -d "$CERT_PATH/$DOMAIN" ]; then
        log_warn "Wildcard certificate already exists. Skipping..."
        return 0
    fi

    # Determine credentials file based on DNS plugin
    case "$DNS_PLUGIN" in
        cloudflare)
            CREDENTIALS_FILE="/root/.secrets/cloudflare.ini"
            PLUGIN_NAME="dns-cloudflare"
            ;;
        route53)
            CREDENTIALS_FILE="/root/.aws/credentials"
            PLUGIN_NAME="dns-route53"
            ;;
        digitalocean)
            CREDENTIALS_FILE="/root/.secrets/digitalocean.ini"
            PLUGIN_NAME="dns-digitalocean"
            ;;
        *)
            log_error "Unsupported DNS plugin: $DNS_PLUGIN"
            log_error "Supported plugins: cloudflare, route53, digitalocean"
            return 1
            ;;
    esac

    # Check if credentials file exists
    if [ ! -f "$CREDENTIALS_FILE" ]; then
        log_error "Credentials file not found: $CREDENTIALS_FILE"
        log_error "Please create the credentials file for your DNS provider."
        return 1
    fi

    # Obtain wildcard certificate
    certbot certonly \
        --"$PLUGIN_NAME" \
        --"$PLUGIN_NAME"-credentials "$CREDENTIALS_FILE" \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$WILDCARD_DOMAIN" \
        -d "$API_DOMAIN" || {
            log_error "Failed to obtain wildcard certificate"
            return 1
        }

    log_info "Wildcard certificate obtained successfully"
}

# ========================================
# Step 3: Test Nginx Configuration
# ========================================
test_nginx_config() {
    log_info "Testing Nginx configuration..."

    if nginx -t; then
        log_info "Nginx configuration is valid"
        return 0
    else
        log_error "Nginx configuration test failed"
        log_error "Please fix the configuration before reloading Nginx"
        return 1
    fi
}

# ========================================
# Step 4: Reload Nginx
# ========================================
reload_nginx() {
    log_info "Reloading Nginx to apply SSL certificates..."

    if systemctl reload nginx; then
        log_info "Nginx reloaded successfully"
    else
        log_error "Failed to reload Nginx"
        return 1
    fi
}

# ========================================
# Step 5: Setup Auto-Renewal
# ========================================
setup_auto_renewal() {
    log_info "Setting up automatic certificate renewal..."

    # Certbot auto-renewal is handled by systemd timer (certbot.timer)
    # Check if timer is enabled
    if systemctl is-enabled certbot.timer &> /dev/null; then
        log_info "Certbot auto-renewal timer is already enabled"
    else
        log_warn "Enabling Certbot auto-renewal timer..."
        systemctl enable certbot.timer
        systemctl start certbot.timer
        log_info "Auto-renewal timer enabled"
    fi

    # Add renewal hook to reload Nginx after renewal
    RENEWAL_HOOK="/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh"
    mkdir -p "$(dirname "$RENEWAL_HOOK")"
    
    cat > "$RENEWAL_HOOK" << 'EOF'
#!/bin/bash
# Reload Nginx after certificate renewal
systemctl reload nginx
EOF
    
    chmod +x "$RENEWAL_HOOK"
    log_info "Nginx reload hook added to renewal process"

    # Test renewal process (dry run)
    log_info "Testing certificate renewal (dry run)..."
    if certbot renew --dry-run; then
        log_info "Certificate renewal test passed"
    else
        log_warn "Certificate renewal test failed (this is non-critical)"
    fi
}

# ========================================
# Step 6: Display Certificate Information
# ========================================
display_cert_info() {
    log_info "Certificate Information:"
    echo ""
    
    if [ -d "$CERT_PATH/$API_DOMAIN" ]; then
        log_info "API Domain: $API_DOMAIN"
        certbot certificates -d "$API_DOMAIN" | grep -E "(Certificate Name|Domains|Expiry Date)"
        echo ""
    fi

    if [ -d "$CERT_PATH/$DOMAIN" ]; then
        log_info "Wildcard Domain: $WILDCARD_DOMAIN"
        certbot certificates | grep -E "(Certificate Name|Domains|Expiry Date)" | head -n 6
        echo ""
    fi

    log_info "Renewal status:"
    systemctl status certbot.timer --no-pager | head -n 10
}

# ========================================
# Main Execution
# ========================================
main() {
    echo "========================================"
    echo "Let's Encrypt SSL Setup for mikan.uz"
    echo "========================================"
    echo ""

    # Check if email is provided
    if [ -z "$CERTBOT_EMAIL" ]; then
        log_warn "CERTBOT_EMAIL environment variable not set"
        log_warn "Using default: $EMAIL"
        echo ""
        read -p "Press Enter to continue or Ctrl+C to abort..."
    fi

    check_prerequisites
    echo ""

    setup_api_cert
    echo ""

    setup_wildcard_cert
    echo ""

    test_nginx_config
    echo ""

    reload_nginx
    echo ""

    setup_auto_renewal
    echo ""

    display_cert_info
    echo ""

    log_info "SSL setup complete!"
    log_info "Your certificates will auto-renew every 60 days"
    log_info ""
    log_info "Next steps:"
    log_info "  1. Update Nginx configuration to use SSL certificates"
    log_info "  2. Test HTTPS access: https://$API_DOMAIN"
    log_info "  3. Test wildcard subdomain: https://center1.$DOMAIN"
    log_info "  4. Monitor renewal: journalctl -u certbot.timer"
}

# Run main function
main "$@"
