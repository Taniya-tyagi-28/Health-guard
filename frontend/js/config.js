/**
 * HealthGuard Frontend API Configuration
 * Supports connecting to local Flask dev server (http://127.0.0.1:5000)
 * or production Render backend (https://healthguard-ovsm.onrender.com).
 */

const DEFAULT_API_URL = "https://healthguard-ovsm.onrender.com";


function getApiBaseUrl() {
    return (
        window.__HEALTHGUARD_API_URL__ ||
        localStorage.getItem("HEALTHGUARD_API_URL") ||
        DEFAULT_API_URL
    ).replace(/\/+$/, "");
}

function setApiBaseUrl(url) {
    if (!url) return;
    const cleanUrl = url.trim().replace(/\/+$/, "");
    localStorage.setItem("HEALTHGUARD_API_URL", cleanUrl);
    window.location.reload();
}

function promptForBackendUrl() {
    const current = getApiBaseUrl();
    const entered = prompt(
        "Enter your Render Backend URL (e.g., https://healthguard-api.onrender.com):",
        current
    );
    if (entered && entered.trim()) {
        setApiBaseUrl(entered.trim());
    }
}

// Health check to update status indicator
async function checkBackendConnection() {
    const apiUrl = getApiBaseUrl();
    const statusDot = document.getElementById("backendStatusDot");
    const statusText = document.getElementById("backendStatusText");
    const backendLabel = document.getElementById("currentBackendLabel");

    if (backendLabel) {
        backendLabel.innerText = apiUrl;
    }

    try {
        const res = await fetch(`${apiUrl}/api/patients`, { method: "GET", headers: { "Accept": "application/json" } });
        if (res.ok) {
            if (statusDot) {
                statusDot.className = "pulse-dot";
                statusDot.style.backgroundColor = "#10b981";
            }
            if (statusText) statusText.innerText = "Backend Connected";
        } else {
            throw new Error(`HTTP ${res.status}`);
        }
    } catch (err) {
        if (statusDot) {
            statusDot.className = "pulse-dot";
            statusDot.style.backgroundColor = "#f43f5e";
        }
        if (statusText) statusText.innerText = "Connecting / Offline";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    checkBackendConnection();
});
