// System Configuration
const CONFIG = {
    ORCHESTRATOR_URL: 'http://localhost:5002',
    ML_GATEWAY_URL: 'http://localhost:5000',
    ML_PRIVACY_URL: 'http://localhost:5001',
    ETHEREUM_URL: 'http://localhost:8545',
    REFRESH_INTERVAL: 5000, // 5 seconds
    FABRIC_PEER_URL: 'localhost:7051'
};

// Global State
let systemState = {
    orchestrator: 'checking',
    mlGateway: 'checking',
    mlPrivacy: 'checking',
    ethereum: 'checking',
    fabric: 'checking',
    startTime: new Date(),
    dataProcessed: 0,
    privacyFiltered: 0,
    blockchainTxs: 0
};

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupNavigation();
    setupEventListeners();
    startSystemMonitoring();
    updateTimestamps();
});

// Initialize the application
function initializeApp() {
    console.log('🚀 Initializing Hybrid Blockchain IoT System Frontend');
    
    // Set initial timestamps
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    
    document.querySelectorAll('#init-time, #tx-init-time, #log-init-time').forEach(el => {
        if (el) el.textContent = timeString;
    });
    
    // Initialize system status
    updateSystemStatus();
    
    // Add initial log entry
    addLogEntry('INFO', 'Frontend interface initialized successfully');
}

// Setup navigation
function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    const sections = document.querySelectorAll('.section');
    
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Remove active class from all links and sections
            navLinks.forEach(l => l.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));
            
            // Add active class to clicked link
            link.classList.add('active');
            
            // Show corresponding section
            const targetId = link.getAttribute('href').substring(1);
            const targetSection = document.getElementById(targetId);
            if (targetSection) {
                targetSection.classList.add('active');
            }
        });
    });
}

// Setup event listeners
function setupEventListeners() {
    // Data ingestion form
    const dataForm = document.getElementById('data-form');
    if (dataForm) {
        dataForm.addEventListener('submit', handleDataSubmission);
    }
    
    // Privacy control sliders
    const gatewayThreshold = document.getElementById('gateway-threshold');
    const privacyThreshold = document.getElementById('privacy-threshold');
    
    if (gatewayThreshold) {
        gatewayThreshold.addEventListener('input', (e) => {
            document.getElementById('gateway-value').textContent = e.target.value + '%';
        });
    }
    
    if (privacyThreshold) {
        privacyThreshold.addEventListener('input', (e) => {
            document.getElementById('privacy-value').textContent = e.target.value + '%';
        });
    }
    
    // Form preview updates
    const formInputs = document.querySelectorAll('#data-form input, #data-form select, #data-form textarea');
    formInputs.forEach(input => {
        input.addEventListener('input', updateDataPreview);
    });
}

// Start system monitoring
function startSystemMonitoring() {
    // Initial check
    checkSystemHealth();
    
    // Set up periodic monitoring
    setInterval(checkSystemHealth, CONFIG.REFRESH_INTERVAL);
    setInterval(updateSystemMetrics, CONFIG.REFRESH_INTERVAL);
}

// Check system health
async function checkSystemHealth() {
    const services = [
        { name: 'orchestrator', url: `${CONFIG.ORCHESTRATOR_URL}/health`, key: 'orchestrator' },
        { name: 'mlGateway', url: `${CONFIG.ML_GATEWAY_URL}/health`, key: 'mlGateway' },
        { name: 'mlPrivacy', url: `${CONFIG.ML_PRIVACY_URL}/health`, key: 'mlPrivacy' }
    ];
    
    // Check HTTP services
    for (const service of services) {
        try {
            const response = await fetch(service.url, { 
                method: 'GET',
                timeout: 5000 
            });
            
            if (response.ok) {
                systemState[service.key] = 'online';
                updateServiceStatus(service.key, 'online');
            } else {
                systemState[service.key] = 'offline';
                updateServiceStatus(service.key, 'offline');
            }
        } catch (error) {
            systemState[service.key] = 'offline';
            updateServiceStatus(service.key, 'offline');
        }
    }
    
    // Check Ethereum
    await checkEthereumStatus();
    
    // Update overall system status
    updateSystemStatus();
}

// Check Ethereum status
async function checkEthereumStatus() {
    try {
        const response = await fetch(CONFIG.ETHEREUM_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'eth_blockNumber',
                params: [],
                id: 1
            }),
            timeout: 5000
        });
        
        if (response.ok) {
            const data = await response.json();
            systemState.ethereum = 'online';
            updateServiceStatus('ethereum', 'online');
            
            // Update block number
            const blockNumber = parseInt(data.result, 16);
            const blockElement = document.getElementById('eth-block');
            if (blockElement) {
                blockElement.textContent = blockNumber;
            }
        } else {
            systemState.ethereum = 'offline';
            updateServiceStatus('ethereum', 'offline');
        }
    } catch (error) {
        systemState.ethereum = 'offline';
        updateServiceStatus('ethereum', 'offline');
    }
}

// Update service status in UI
function updateServiceStatus(service, status) {
    const statusElement = document.getElementById(`${service}-status`);
    if (statusElement) {
        statusElement.textContent = status === 'online' ? 'Online' : 'Offline';
        statusElement.className = `status-badge ${status}`;
    }
    
    // Update detailed service list
    updateDetailedServiceStatus(service, status);
}

// Update detailed service status
function updateDetailedServiceStatus(service, status) {
    const serviceList = document.getElementById('service-list');
    if (!serviceList) return;
    
    const serviceNames = {
        orchestrator: 'System Orchestrator',
        mlGateway: 'ML Gateway Filter',
        mlPrivacy: 'ML Privacy Filter',
        ethereum: 'Ethereum Node',
        fabric: 'Hyperledger Fabric'
    };
    
    let serviceItem = document.querySelector(`[data-service="${service}"]`);
    if (!serviceItem) {
        serviceItem = document.createElement('div');
        serviceItem.className = 'service-item';
        serviceItem.setAttribute('data-service', service);
        serviceList.appendChild(serviceItem);
    }
    
    serviceItem.innerHTML = `
        <span class="service-name">${serviceNames[service]}</span>
        <span class="status-badge ${status}">${status === 'online' ? 'Online' : 'Offline'}</span>
    `;
}

// Update system status
function updateSystemStatus() {
    const services = Object.values(systemState).slice(0, 5); // First 5 are service statuses
    const onlineServices = services.filter(status => status === 'online').length;
    const totalServices = services.length;
    
    // Update system health indicator (you can add this to your UI)
    console.log(`System Health: ${onlineServices}/${totalServices} services online`);
}

// Update system metrics
function updateSystemMetrics() {
    const now = new Date();
    const uptime = Math.floor((now - systemState.startTime) / 1000);
    
    // Format uptime
    const hours = Math.floor(uptime / 3600);
    const minutes = Math.floor((uptime % 3600) / 60);
    const seconds = uptime % 60;
    const uptimeString = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    
    // Update UI elements
    const uptimeElement = document.getElementById('system-uptime');
    if (uptimeElement) uptimeElement.textContent = uptimeString;
    
    const dataProcessedElement = document.getElementById('data-processed');
    if (dataProcessedElement) dataProcessedElement.textContent = systemState.dataProcessed;
    
    const privacyFilteredElement = document.getElementById('privacy-filtered');
    if (privacyFilteredElement) privacyFilteredElement.textContent = systemState.privacyFiltered;
    
    const blockchainTxsElement = document.getElementById('blockchain-txs');
    if (blockchainTxsElement) blockchainTxsElement.textContent = systemState.blockchainTxs;
}

// Handle data submission
async function handleDataSubmission(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const deviceId = formData.get('device-id') || document.getElementById('device-id').value;
    const location = formData.get('location') || document.getElementById('location').value;
    const dataType = formData.get('data-type') || document.getElementById('data-type').value;
    const dataPayload = formData.get('data-payload') || document.getElementById('data-payload').value;
    const privacyLevel = formData.get('privacy-level') || document.getElementById('privacy-level').value;
    
    // Validate JSON payload
    let parsedData;
    try {
        parsedData = JSON.parse(dataPayload);
    } catch (error) {
        showError('Invalid JSON format in data payload');
        return;
    }
    
    // Prepare submission data
    const submissionData = {
        id: `${deviceId}_${Date.now()}`,
        deviceId: deviceId,
        timestamp: new Date().toISOString(),
        location: location,
        dataType: dataType,
        privacyLevel: privacyLevel,
        data: parsedData
    };
    
    // Show loading state
    const submitButton = e.target.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.innerHTML = '<div class="loading"></div> Processing...';
    submitButton.disabled = true;
    
    try {
        // Submit to orchestrator
        const response = await fetch(`${CONFIG.ORCHESTRATOR_URL}/ingest_data`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(submissionData)
        });
        
        const result = await response.text();
        
        // Show results
        showSubmissionResults(response.ok, result, submissionData);
        
        if (response.ok) {
            // Update metrics
            systemState.dataProcessed++;
            systemState.privacyFiltered++;
            systemState.blockchainTxs++;
            
            // Add activity
            addActivity(`Data submitted from ${deviceId}`, 'success');
            addLogEntry('SUCCESS', `IoT data processed successfully: ${deviceId}`);
            
            // Reset form
            e.target.reset();
            updateDataPreview();
        } else {
            addLogEntry('ERROR', `Data submission failed: ${result}`);
        }
        
    } catch (error) {
        showSubmissionResults(false, error.message, submissionData);
        addLogEntry('ERROR', `Network error during data submission: ${error.message}`);
    } finally {
        // Restore button
        submitButton.innerHTML = originalText;
        submitButton.disabled = false;
    }
}

// Show submission results
function showSubmissionResults(success, message, data) {
    const resultsContainer = document.getElementById('results-container');
    const resultsContent = document.getElementById('results-content');
    
    if (!resultsContainer || !resultsContent) return;
    
    resultsContainer.style.display = 'block';
    
    const statusClass = success ? 'success' : 'error';
    const statusIcon = success ? 'fas fa-check-circle' : 'fas fa-exclamation-circle';
    const statusText = success ? 'Success' : 'Error';
    
    resultsContent.innerHTML = `
        <div class="result-status ${statusClass}">
            <i class="${statusIcon}"></i>
            <span>${statusText}</span>
        </div>
        <div class="result-details">
            <h4>Submission Details:</h4>
            <p><strong>Device ID:</strong> ${data.deviceId}</p>
            <p><strong>Timestamp:</strong> ${data.timestamp}</p>
            <p><strong>Location:</strong> ${data.location}</p>
            <p><strong>Data Type:</strong> ${data.dataType}</p>
            <p><strong>Privacy Level:</strong> ${data.privacyLevel}</p>
        </div>
        <div class="result-message">
            <h4>Response:</h4>
            <pre>${message}</pre>
        </div>
    `;
    
    // Auto-hide after 10 seconds
    setTimeout(() => {
        resultsContainer.style.display = 'none';
    }, 10000);
}

// Update data preview
function updateDataPreview() {
    const deviceId = document.getElementById('device-id')?.value || '';
    const location = document.getElementById('location')?.value || '';
    const dataType = document.getElementById('data-type')?.value || '';
    const dataPayload = document.getElementById('data-payload')?.value || '';
    const privacyLevel = document.getElementById('privacy-level')?.value || '';
    
    const previewContent = document.getElementById('preview-content');
    if (!previewContent) return;
    
    if (!deviceId && !location && !dataType && !dataPayload) {
        previewContent.innerHTML = '<p>Fill out the form to see how your data will be processed...</p>';
        return;
    }
    
    let parsedData = {};
    try {
        if (dataPayload) {
            parsedData = JSON.parse(dataPayload);
        }
    } catch (error) {
        parsedData = { error: 'Invalid JSON format' };
    }
    
    previewContent.innerHTML = `
        <div class="preview-section">
            <h4>📊 Data Processing Flow:</h4>
            <div class="preview-flow">
                <div class="preview-step">
                    <strong>1. Data Ingestion</strong>
                    <p>Device: ${deviceId || 'Not specified'}</p>
                    <p>Location: ${location || 'Not specified'}</p>
                </div>
                <div class="preview-step">
                    <strong>2. ML Gateway Filter</strong>
                    <p>Data Type: ${dataType || 'Not specified'}</p>
                    <p>Sensitivity Analysis: ${privacyLevel || 'Not specified'}</p>
                </div>
                <div class="preview-step">
                    <strong>3. Blockchain Storage</strong>
                    <p>Private: Full data → Hyperledger Fabric</p>
                    <p>Public: Metadata → Ethereum</p>
                </div>
            </div>
        </div>
        <div class="preview-section">
            <h4>🔒 Privacy Processing:</h4>
            <p><strong>Privacy Level:</strong> ${privacyLevel || 'Not specified'}</p>
            <p><strong>ML Filter Action:</strong> ${getPrivacyAction(privacyLevel)}</p>
        </div>
        <div class="preview-section">
            <h4>📋 Data Payload:</h4>
            <pre>${JSON.stringify(parsedData, null, 2)}</pre>
        </div>
    `;
}

// Get privacy action description
function getPrivacyAction(level) {
    switch (level) {
        case 'high':
            return 'Minimal metadata shared publicly, full data encrypted in private chain';
        case 'medium':
            return 'Balanced sharing with anonymized identifiers';
        case 'low':
            return 'Maximum transparency while maintaining security';
        default:
            return 'Select privacy level to see action';
    }
}

// Add activity to the activity list
function addActivity(message, type = 'info') {
    const activityList = document.getElementById('activity-list');
    if (!activityList) return;
    
    const activityItem = document.createElement('div');
    activityItem.className = 'activity-item';
    
    const icon = type === 'success' ? 'fas fa-check-circle' : 
                 type === 'error' ? 'fas fa-exclamation-circle' : 
                 'fas fa-info-circle';
    
    activityItem.innerHTML = `
        <i class="${icon}"></i>
        <span>${message}</span>
        <time>${new Date().toLocaleTimeString()}</time>
    `;
    
    activityList.insertBefore(activityItem, activityList.firstChild);
    
    // Keep only last 10 activities
    while (activityList.children.length > 10) {
        activityList.removeChild(activityList.lastChild);
    }
}

// Add log entry
function addLogEntry(level, message) {
    const logsContent = document.getElementById('logs-content');
    if (!logsContent) return;
    
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    
    const time = new Date().toLocaleTimeString();
    logEntry.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-level ${level.toLowerCase()}">${level}</span>
        <span class="log-message">${message}</span>
    `;
    
    logsContent.insertBefore(logEntry, logsContent.firstChild);
    
    // Keep only last 20 log entries
    while (logsContent.children.length > 20) {
        logsContent.removeChild(logsContent.lastChild);
    }
    
    // Auto-scroll to top
    logsContent.scrollTop = 0;
}

// Update timestamps
function updateTimestamps() {
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    
    // Update any timestamp elements that need current time
    document.querySelectorAll('.current-time').forEach(el => {
        el.textContent = timeString;
    });
}

// Utility functions for blockchain interactions
async function queryFabricData() {
    addLogEntry('INFO', 'Querying Hyperledger Fabric data...');
    // Implementation would depend on your Fabric query endpoints
    showInfo('Fabric query functionality would be implemented based on your specific chaincode');
}

async function queryEthereumData() {
    addLogEntry('INFO', 'Querying Ethereum registry...');
    try {
        const response = await fetch(CONFIG.ETHEREUM_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'eth_getBalance',
                params: ['0x0000000000000000000000000000000000000000', 'latest'],
                id: 1
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            showInfo(`Ethereum query successful: ${data.result}`);
            addLogEntry('SUCCESS', 'Ethereum registry queried successfully');
        }
    } catch (error) {
        addLogEntry('ERROR', `Ethereum query failed: ${error.message}`);
    }
}

// ML Service Testing Functions
async function testMLGateway() {
    addLogEntry('INFO', 'Testing ML Gateway Filter...');
    try {
        const response = await fetch(`${CONFIG.ML_GATEWAY_URL}/health`);
        if (response.ok) {
            const data = await response.json();
            showInfo(`ML Gateway Test: ${data.message}`);
            addLogEntry('SUCCESS', 'ML Gateway test completed successfully');
        }
    } catch (error) {
        addLogEntry('ERROR', `ML Gateway test failed: ${error.message}`);
    }
}

async function testMLPrivacy() {
    addLogEntry('INFO', 'Testing ML Privacy Filter...');
    try {
        const response = await fetch(`${CONFIG.ML_PRIVACY_URL}/health`);
        if (response.ok) {
            const data = await response.json();
            showInfo(`ML Privacy Filter Test: ${data.message}`);
            addLogEntry('SUCCESS', 'ML Privacy Filter test completed successfully');
        }
    } catch (error) {
        addLogEntry('ERROR', `ML Privacy Filter test failed: ${error.message}`);
    }
}

// View logs functions
function viewFabricLogs() {
    addLogEntry('INFO', 'Viewing Hyperledger Fabric logs...');
    showInfo('Fabric logs would be displayed here in a production implementation');
}

function viewEthereumLogs() {
    addLogEntry('INFO', 'Viewing Ethereum logs...');
    showInfo('Ethereum logs would be displayed here in a production implementation');
}

// Utility functions for user feedback
function showError(message) {
    console.error(message);
    addLogEntry('ERROR', message);
    // You could add a toast notification system here
}

function showInfo(message) {
    console.info(message);
    addLogEntry('INFO', message);
    // You could add a toast notification system here
}

function showSuccess(message) {
    console.log(message);
    addLogEntry('SUCCESS', message);
    // You could add a toast notification system here
}

// Export functions for global access
window.testMLGateway = testMLGateway;
window.testMLPrivacy = testMLPrivacy;
window.queryFabricData = queryFabricData;
window.queryEthereumData = queryEthereumData;
window.viewFabricLogs = viewFabricLogs;
window.viewEthereumLogs = viewEthereumLogs;
