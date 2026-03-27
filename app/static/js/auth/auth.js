/* Auth JWT token management, API calls with auth, and redirects */

// Get URL prefix from HTML data attribute (default to /v1 if not found)
const URL_PREFIX = document.documentElement.getAttribute('data-url-prefix');
const LOGIN_URL = document.documentElement.getAttribute('data-login-url');
const LOGOUT_URL = document.documentElement.getAttribute('data-logout-url');
const REGISTER_URL = document.documentElement.getAttribute('data-register-url');
const REFRESH_URL = document.documentElement.getAttribute('data-refresh-url');

const AUTH = {
	// Token storage
	getAccessToken() {
		return localStorage.getItem('access_token');
	},

	getRefreshToken() {
		return localStorage.getItem('refresh_token');
	},

	setTokens(accessToken, refreshToken) {
		localStorage.setItem('access_token', accessToken);
		localStorage.setItem('refresh_token', refreshToken);
	},

	clearTokens() {
		localStorage.removeItem('access_token');
		localStorage.removeItem('refresh_token');
	},

	isLoggedIn() {
		return !!this.getAccessToken();
	},

	// API calls with automatic auth header (endpoint must be a full URL path)
	async request(endpoint, options = {}) {
		const url = endpoint;
		const headers = {
			...options.headers,
		};
		
		// Add auth header if logged in
		const token = this.getAccessToken();
		if (token) {
			headers['Authorization'] = `Bearer ${token}`;
		}
		
		let response = await fetch(url, {
			...options,
			headers,
		});
		
		// If token expired (401), try to refresh
		if (response.status === 401 && token) {
			const refreshed = await this.refreshToken();
			if (refreshed) {
				// Retry request with new token
				const newToken = this.getAccessToken();
				headers['Authorization'] = `Bearer ${newToken}`;
				response = await fetch(url, {
					...options,
					headers,
				});
			} else {
				// Refresh failed, redirect to login
				this.clearTokens();
				window.location.href = LOGIN_URL;
				return null;
			}
		}
		
		return response;
	},

	// Refresh access token
	async refreshToken() {
		const refreshToken = this.getRefreshToken();
		if (!refreshToken) return false;
		
		try {
			const response = await AUTH.request(REFRESH_URL, {
				method: 'POST',
				headers: {'Content-Type': 'application/json'},
				body: JSON.stringify({ refresh_token: refreshToken }),
		});
		
			if (response.ok) {
				const data = await response.json();
				this.setTokens(data.access_token, data.refresh_token);
				return true;
			}
		} catch (error) {
			console.error('Token refresh failed:', error);
		}
		
		return false;
	},

	// Register
	async register(username, email, password, is_admin = false) {
		const response = await this.request(REGISTER_URL, {
			method: 'POST',
			headers: {'Content-Type': 'application/json'},
			body: JSON.stringify({ username, email, password, is_admin }),
		});
		
		if (!response.ok) {
			// Read body once, then try to parse as JSON
			const bodyText = await response.text();
			let errorMessage = 'Registration failed';
			try {
				const error = JSON.parse(bodyText);
				errorMessage = error.detail || 'Registration failed';
			} catch (e) {
				errorMessage = `Server error: ${bodyText}`;
			}
			console.error('Server response:', bodyText);
			throw new Error(errorMessage);
		}
		
		return await response.json();
	},

	// Login
	async login(username, password) {
		const response = await AUTH.request(LOGIN_URL, {
			method: 'POST',
			headers: {'Content-Type': 'application/json'},
			body: JSON.stringify({ username, password }),
		});
		
		if (!response.ok) {
			// Read body once, then try to parse as JSON
			const bodyText = await response.text();
			let errorMessage = 'Login failed';
			try {
				const error = JSON.parse(bodyText);
				errorMessage = error.detail || 'Login failed';
			} catch (e) {
				console.error('Server response:', bodyText);
				errorMessage = `Server error: ${bodyText}`;
			}
			console.error('Server response:', bodyText);
			throw new Error(errorMessage);
		}
		
		const data = await response.json();
		this.setTokens(data.access_token, data.refresh_token);
		return data;
	},

	// Logout
	async logout() {
		try {
			await this.request(LOGOUT_URL, { method: 'POST' });
		} catch (error) {
			console.error('Logout error:', error);
		}
		
		this.clearTokens();
		window.location.href = `${URL_PREFIX}/`;
	},
};

/**
 * Update UI based on login status
 */
function updateAuthUI() {
	const authButton = document.getElementById('auth-button');
	const userInfo = document.getElementById('user-info');

	if (!authButton) return; // Auth button not on this page

	if (AUTH.isLoggedIn()) {
		// Show logout button
		authButton.innerHTML = 'Logout';
		authButton.onclick = (e) => {
			e.preventDefault();
			AUTH.logout();
		};
		userInfo.style.display = 'block';
	} else {
		// Show login button
		authButton.innerHTML = 'Login';
		authButton.onclick = (e) => {
			e.preventDefault();
			window.location.href = LOGIN_URL;
		};
		userInfo.style.display = 'none';
	}
}

// Run on page load
document.addEventListener('DOMContentLoaded', updateAuthUI);
