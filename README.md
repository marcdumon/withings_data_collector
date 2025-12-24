# Withings Data Collector

A Python application for collecting and managing data from the Withings API.

## Setup

### Prerequisites

- Python 3.13+
- Withings Developer Account

### Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   uv sync
   ```
   Or with pip:
   ```bash
   pip install -e .
   ```

3. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

4. Configure your `.env` file with your Withings API credentials (see below)

## Getting API Credentials

To use the Withings API, you need to create an application in the Withings Developer Dashboard and obtain your credentials.

### Step 1: Create a Withings Developer Account

Visit the Withings Partner Hub:
- **Dashboard URL**: https://developer.withings.com/dashboard/
- **Documentation**: https://developer.withings.com/

### Step 2: Create a New Application

1. Log in to the [Withings Developer Dashboard](https://developer.withings.com/dashboard/)
2. Click "Create Application" or select your existing application
3. Fill in the application details:
   - **Application Name**: This name will be shown to users during authorization
   - **Description**: Brief description of your application
   - **Callback URL**: Your redirect URI (e.g., `https://localhost:123/redirect`)
     - For development: You can use `https://localhost:PORT/path`
     - Note: localhost URLs are limited to 10 users in development
     - For production: Use a proper HTTPS URL (port 443)

### Step 3: Get Your Credentials

After creating your application, you'll receive:

- **Client ID**: Your application's unique identifier
- **Client Secret**: Your application's secret key (keep this secure!)
- **Callback URL**: The redirect URI you registered

**Important URLs:**
- **Developer Dashboard**: https://developer.withings.com/dashboard/
- **API Documentation**: https://developer.withings.com/developer-guide/v3/
- **OAuth2 Guide**: https://developer.withings.com/developer-guide/v3/integration-guide/advanced-research-api/get-access/oauth-web-flow

### Step 4: Configure Your .env File

Edit your `.env` file and add your credentials:

```env
WITHINGS_CLIENT_ID=your_client_id_here
WITHINGS_CLIENT_SECRET=your_client_secret_here
WITHINGS_REDIRECT_URI=https://localhost:123/redirect
```

**Important**: The `WITHINGS_REDIRECT_URI` must match EXACTLY what you registered in the dashboard (including protocol, port, and path).

## Using get_auth_code.py

The `get_auth_code.py` script handles the OAuth2 authorization flow to obtain access and refresh tokens from the Withings API.

### Purpose

This script automates the process of:
1. Opening the Withings authorization page in your browser
2. Prompting you to copy and paste the authorization code from the redirect URL
3. Exchanging the authorization code for access and refresh tokens
4. Saving the tokens to your `.env` file for future use

### Running the Script

```bash
python -m withings_data_collector.get_auth_code
```

Or if running directly:

```bash
python src/withings_data_collector/get_auth_code.py
```

### Step-by-Step Process

1. **Check Configuration**
   - The script verifies that your `.env` file exists and contains required credentials
   - If missing, you'll see an error message with instructions

2. **Authorization Flow**
   - The script opens your browser to the Withings authorization page
   - You (or the user) must log in and authorize the application
   - After authorization, Withings redirects to your callback URL

3. **Collect Authorization Code**
   - Copy the full redirect URL from your browser's address bar
   - The URL will look like: `https://localhost:123/redirect?code=AUTHORIZATION_CODE&state=...`
   - Paste this URL when prompted by the script
   - The script automatically extracts the authorization code

4. **Token Exchange**
   - The script exchanges the authorization code for access and refresh tokens
   - This happens automatically via the Withings API

5. **Save Tokens**
   - Upon success, the tokens are automatically saved to your `.env` file:
     - `WITHINGS_ACCESS_TOKEN`
     - `WITHINGS_REFRESH_TOKEN`

### Important Notes

- **Authorization codes expire in ~30 seconds** - be quick when copying and pasting
- **Authorization codes can only be used once** - if you need new tokens, run the script again
- **Access tokens expire in ~3 hours** - use refresh tokens to get new access tokens without re-authorization
- **Refresh tokens** - stored in `.env`, can be used to refresh access tokens without user interaction

### Troubleshooting

#### "Redirect URI mismatch" Error

**Problem**: The redirect URI in your `.env` doesn't match what's registered in the dashboard.

**Solution**: 
1. Check your `.env` file: `WITHINGS_REDIRECT_URI` must match exactly
2. Verify in the dashboard: https://developer.withings.com/dashboard/
3. Ensure exact match including:
   - Protocol (http vs https)
   - Port number
   - Path
   - Trailing slashes (or lack thereof)

#### "Invalid Client ID or Secret" Error

**Problem**: Your credentials don't match what's in the dashboard.

**Solution**:
1. Go to https://developer.withings.com/dashboard/
2. Copy your Client ID and Secret exactly (use the copy button, don't type)
3. Update your `.env` file with the exact values
4. Make sure there are no extra spaces or characters

#### Rate Limiting

**Problem**: You see a rate limit error (status 601).

**Solution**:
1. Wait the suggested amount of time
2. Get a fresh authorization code (run the authorization flow again)
3. Don't run the script multiple times in quick succession
4. Rate limits are per client_id - avoid rapid repeated attempts

#### Browser Doesn't Open Automatically

**Problem**: The browser doesn't open when the script runs.

**Solution**:
1. The script will show the authorization URL in the terminal
2. Copy and paste it into your browser manually
3. Continue with the normal flow

### Configuration Files

- **`.env`**: Contains your credentials and tokens (not tracked in git)
- **`.env.example`**: Template showing required environment variables
- **`src/withings_data_collector/config.py`**: API endpoint configuration

### Security Notes

- Never commit your `.env` file to version control
- Keep your Client Secret secure
- Don't share your access tokens
- Refresh tokens provide long-term access - protect them

## Additional Resources

- **Withings Developer Documentation**: https://developer.withings.com/developer-guide/v3/
- **OAuth2 Web Flow Guide**: https://developer.withings.com/developer-guide/v3/integration-guide/advanced-research-api/get-access/oauth-web-flow
- **API Reference**: https://developer.withings.com/api-reference
- **Support**: Check the Withings developer documentation or contact Withings support through the dashboard

