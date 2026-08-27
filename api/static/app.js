/**
 * Nokia GPON Gateway Control Center Frontend Application
 */

const AppState = {
    devices: [],
    filter: 'all',
    searchQuery: '',
    autoRefresh: false,
    refreshIntervalId: null,
    loading: false,
    pendingActions: {}, // { [mac_lowercase]: 'blocking' | 'unblocking' }
};

// DOM Elements
const elements = {
    tbody: document.getElementById('device-tbody'),
    searchInput: document.getElementById('search-input'),
    clearSearchBtn: document.getElementById('clear-search'),
    filterTabs: document.querySelectorAll('.filter-tab'),
    btnRefresh: document.getElementById('btn-refresh'),
    refreshIcon: document.getElementById('refresh-icon'),
    statusBadge: document.getElementById('router-status-badge'),
    autoRefreshCheck: document.getElementById('auto-refresh-check'),

    // Stats
    statTotal: document.getElementById('stat-total'),
    statActive: document.getElementById('stat-active'),
    statBlocked: document.getElementById('stat-blocked'),
    statNicknames: document.getElementById('stat-nicknames'),

    // Filter counts
    countAll: document.getElementById('count-all'),
    countActive: document.getElementById('count-active'),
    countBlocked: document.getElementById('count-blocked'),
    countCustom: document.getElementById('count-custom'),

    // Modal elements
    modal: document.getElementById('nickname-modal'),
    modalForm: document.getElementById('nickname-form'),
    modalMacInput: document.getElementById('modal-mac-input'),
    modalNickInput: document.getElementById('modal-nickname-input'),
    modalNotesInput: document.getElementById('modal-notes-input'),
    modalHostText: document.getElementById('modal-device-hostname'),
    modalMacText: document.getElementById('modal-device-mac'),
    closeModalBtn: document.getElementById('close-modal-btn'),
    cancelModalBtn: document.getElementById('btn-cancel-modal'),
    clearNicknameBtn: document.getElementById('btn-clear-nickname'),

    toastContainer: document.getElementById('toast-container'),
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    checkHealth();
    fetchDevices();
});

function bindEvents() {
    // Refresh button
    elements.btnRefresh.addEventListener('click', () => {
        fetchDevices();
    });

    // Search input
    elements.searchInput.addEventListener('input', (e) => {
        AppState.searchQuery = e.target.value.trim().toLowerCase();
        elements.clearSearchBtn.style.display = AppState.searchQuery ? 'block' : 'none';
        renderDevices();
    });

    // Clear search
    elements.clearSearchBtn.addEventListener('click', () => {
        elements.searchInput.value = '';
        AppState.searchQuery = '';
        elements.clearSearchBtn.style.display = 'none';
        renderDevices();
    });

    // Filter tabs
    elements.filterTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            elements.filterTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            AppState.filter = tab.dataset.filter;
            renderDevices();
        });
    });

    // Auto refresh toggle
    elements.autoRefreshCheck.addEventListener('change', (e) => {
        AppState.autoRefresh = e.target.checked;
        if (AppState.autoRefresh) {
            AppState.refreshIntervalId = setInterval(fetchDevices, 10000);
            showToast('Auto-sync enabled (10s interval)', 'info');
        } else {
            clearInterval(AppState.refreshIntervalId);
            AppState.refreshIntervalId = null;
            showToast('Auto-sync paused', 'info');
        }
    });

    // Modal controls
    elements.closeModalBtn.addEventListener('click', closeModal);
    elements.cancelModalBtn.addEventListener('click', closeModal);
    elements.modal.addEventListener('click', (e) => {
        if (e.target === elements.modal) closeModal();
    });

    // Modal Form Submit
    elements.modalForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const mac = elements.modalMacInput.value;
        const nickname = elements.modalNickInput.value.trim();
        const notes = elements.modalNotesInput.value.trim();
        await saveNickname(mac, nickname, notes);
        closeModal();
    });

    // Clear Nickname Button
    elements.clearNicknameBtn.addEventListener('click', async () => {
        const mac = elements.modalMacInput.value;
        await saveNickname(mac, null, null);
        closeModal();
    });
}

// Router Health Status
async function checkHealth() {
    try {
        const res = await fetch('/api/health');
        const data = await res.json();
        if (data.authenticated) {
            elements.statusBadge.innerHTML = `
                <span class="status-dot online"></span>
                <span class="status-label">Router Connected</span>
            `;
        } else {
            elements.statusBadge.innerHTML = `
                <span class="status-dot pulse"></span>
                <span class="status-label">Authenticating...</span>
            `;
        }
    } catch (err) {
        elements.statusBadge.innerHTML = `
            <span class="status-dot offline"></span>
            <span class="status-label">Offline</span>
        `;
    }
}

// Fetch Devices
async function fetchDevices() {
    if (AppState.loading) return;
    AppState.loading = true;
    elements.refreshIcon.classList.add('spinning');

    try {
        const res = await fetch('/api/devices');
        if (!res.ok) throw new Error('Failed to fetch devices');
        const devices = await res.json();
        // Preserve any ongoing local in-flight pending action
        devices.forEach(d => {
            const pending = AppState.pendingActions[d.mac.toLowerCase()];
            if (pending === 'blocking') {
                d.is_blocked = false;
            } else if (pending === 'unblocking') {
                d.is_blocked = true;
            }
        });
        AppState.devices = devices;
        updateStats();
        renderDevices();
        checkHealth();
    } catch (err) {
        console.error(err);
        showToast('Error communicating with router: ' + err.message, 'error');
    } finally {
        AppState.loading = false;
        elements.refreshIcon.classList.remove('spinning');
    }
}

// Update Stats & Counts
function updateStats() {
    const total = AppState.devices.length;
    const active = AppState.devices.filter(d => d.active).length;
    const blocked = AppState.devices.filter(d => d.is_blocked).length;
    const custom = AppState.devices.filter(d => d.nickname).length;

    elements.statTotal.textContent = total;
    elements.statActive.textContent = active;
    elements.statBlocked.textContent = blocked;
    elements.statNicknames.textContent = custom;

    elements.countAll.textContent = total;
    elements.countActive.textContent = active;
    elements.countBlocked.textContent = blocked;
    elements.countCustom.textContent = custom;
}

// Filter and Render Devices Table
function renderDevices() {
    let list = [...AppState.devices];

    // Filter by tab
    if (AppState.filter === 'active') {
        list = list.filter(d => d.active);
    } else if (AppState.filter === 'blocked') {
        list = list.filter(d => d.is_blocked);
    } else if (AppState.filter === 'custom') {
        list = list.filter(d => d.nickname);
    }

    // Filter by search
    if (AppState.searchQuery) {
        const q = AppState.searchQuery;
        list = list.filter(d =>
            (d.nickname && d.nickname.toLowerCase().includes(q)) ||
            (d.hostname && d.hostname.toLowerCase().includes(q)) ||
            (d.ip && d.ip.toLowerCase().includes(q)) ||
            (d.mac && d.mac.toLowerCase().includes(q))
        );
    }

    if (list.length === 0) {
        elements.tbody.innerHTML = `
            <tr>
                <td colspan="8" class="empty-state">
                    <i class="ri-inbox-line" style="font-size: 32px; display: block; margin-bottom: 8px;"></i>
                    <p>No devices found matching current filters.</p>
                </td>
            </tr>
        `;
        return;
    }

    elements.tbody.innerHTML = list.map(device => {
        const macKey = device.mac.toLowerCase();
        const pending = AppState.pendingActions[macKey];

        const nicknameHtml = device.nickname
            ? `<div class="nickname-cell"><span class="nickname-badge"><i class="ri-price-tag-3-line"></i> ${escapeHtml(device.nickname)}</span><button class="btn-edit-nick" onclick="openNicknameModal('${device.mac}')" title="Edit Nickname"><i class="ri-edit-line"></i></button></div>`
            : `<div class="nickname-cell"><span class="no-nickname">No nickname</span><button class="btn-edit-nick" onclick="openNicknameModal('${device.mac}')" title="Add Nickname"><i class="ri-add-line"></i></button></div>`;

        const statusBadge = device.active
            ? `<span class="badge badge-online"><i class="ri-checkbox-circle-fill"></i> Online</span>`
            : `<span class="badge badge-offline"><i class="ri-time-line"></i> Offline</span>`;

        let accessBadge = '';
        let actionBtn = '';

        if (pending === 'blocking') {
            accessBadge = `<span class="badge badge-pending"><i class="ri-loader-4-line spinning"></i> Blocking...</span>`;
            actionBtn = `<button class="btn btn-danger btn-sm btn-loading" disabled>
                            <i class="ri-loader-4-line spinning"></i> Blocking...
                         </button>`;
        } else if (pending === 'unblocking') {
            accessBadge = `<span class="badge badge-pending"><i class="ri-loader-4-line spinning"></i> Unblocking...</span>`;
            actionBtn = `<button class="btn btn-success btn-sm btn-loading" disabled>
                            <i class="ri-loader-4-line spinning"></i> Unblocking...
                         </button>`;
        } else if (device.is_blocked) {
            accessBadge = `<span class="badge badge-blocked"><i class="ri-close-circle-fill"></i> Blocked</span>`;
            actionBtn = `<button class="btn btn-success btn-sm" onclick="toggleBlock('${device.mac}', false)">
                            <i class="ri-lock-unlock-line"></i> Unblock
                         </button>`;
        } else {
            accessBadge = `<span class="badge badge-allowed"><i class="ri-shield-check-fill"></i> Allowed</span>`;
            actionBtn = `<button class="btn btn-danger btn-sm" onclick="toggleBlock('${device.mac}', true)">
                            <i class="ri-forbid-2-line"></i> Block
                         </button>`;
        }

        return `
            <tr id="row-${device.mac.replace(/:/g, '')}">
                <td>${nicknameHtml}</td>
                <td><strong>${escapeHtml(device.hostname || '(unknown)')}</strong></td>
                <td><span class="ip-text">${escapeHtml(device.ip || '-')}</span></td>
                <td><span class="mono-text">${escapeHtml(device.mac)}</span></td>
                <td><span class="iface-tag">${escapeHtml(device.interface || '-')}</span></td>
                <td>${statusBadge}</td>
                <td>${accessBadge}</td>
                <td class="text-right">${actionBtn}</td>
            </tr>
        `;
    }).join('');
}

// Open Nickname Modal
window.openNicknameModal = function(mac) {
    const device = AppState.devices.find(d => d.mac.toLowerCase() === mac.toLowerCase());
    if (!device) return;

    elements.modalMacInput.value = device.mac;
    elements.modalHostText.textContent = device.hostname || '(unknown)';
    elements.modalMacText.textContent = device.mac;
    elements.modalNickInput.value = device.nickname || '';
    elements.modalNotesInput.value = '';

    elements.modal.classList.add('active');
    setTimeout(() => elements.modalNickInput.focus(), 100);
};

function closeModal() {
    elements.modal.classList.remove('active');
}

// Save Nickname API Call
async function saveNickname(mac, nickname, notes) {
    try {
        const res = await fetch('/api/devices/nickname', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: mac, nickname, notes }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to save nickname');

        showToast(data.message || 'Nickname updated!', 'success');
        // Update locally
        const dev = AppState.devices.find(d => d.mac.toLowerCase() === mac.toLowerCase());
        if (dev) dev.nickname = nickname;
        updateStats();
        renderDevices();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// Block / Unblock Toggle API Call with explicit in-flight state tracking
window.toggleBlock = async function(mac, shouldBlock) {
    const macKey = mac.toLowerCase();
    AppState.pendingActions[macKey] = shouldBlock ? 'blocking' : 'unblocking';
    renderDevices();

    const endpoint = shouldBlock ? '/api/block' : '/api/unblock';
    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: mac }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || (shouldBlock ? 'Failed to block device' : 'Failed to unblock device'));

        showToast(data.message, 'success');
        const dev = AppState.devices.find(d => d.mac.toLowerCase() === macKey);
        if (dev) dev.is_blocked = shouldBlock;
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        delete AppState.pendingActions[macKey];
        updateStats();
        renderDevices();
    }
};

// Toast Notifications
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let icon = 'ri-information-line';
    if (type === 'success') icon = 'ri-checkbox-circle-line';
    if (type === 'error') icon = 'ri-error-warning-line';

    toast.innerHTML = `<i class="${icon}" style="font-size: 18px;"></i> <span>${escapeHtml(message)}</span>`;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// Utility: Escape HTML
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
