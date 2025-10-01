// Enhanced Frontend Script with Better UX and Real-time Updates

// System Configuration
const CONFIG = {
    ORCHESTRATOR_URL: 'http://localhost:5002',
    ML_GATEWAY_URL: 'http://localhost:5000',
    ML_PRIVACY_URL: 'http://localhost:5001',
    ETHEREUM_URL: 'http://localhost:8545',
    REFRESH_INTERVAL: 3000, // 3 seconds
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
    blockchainTxs: 0,
    recentTransactions: []
};

// Sample data templates for quick testing
const SAMPLE_DATA = {
    environmental: {
        deviceId: 'env_sensor_001',
        location: 'Building A - Floor 3',
        dataType: 'environmental',
        privacyLevel: 'medium',
        data: {
            temperature: 22.5,
            humidity: 65,
            pressure: 1013.25,
            airQuality: 'good',
            co2Level: 400
        }
    },
    medical: {
        deviceId: 'medical_monitor_042',
        location: 'Hospital Ward 5',
        dataType: 'medical',
        privacyLevel: 'high',
        data: {
            heartRate: 75,
            bloodPressure: '118/76',
            temperature: 36.8,
            oxygenLevel: 98,
            patientId: 'anonymous_001'
        }
    },
    industrial: {
        deviceId: 'industrial_sensor_099',
        location: 'Factory Floor 2',
        dataType: 'industrial',
        privacyLevel: 'medium',
        data: {
            machineId: 'CNC_001',
            vibration: 2.3,
            temperature: 45.2,
            operatingHours: 1250,
            efficiency: 94.5
        }
    },
    security: {
        deviceId: 'security_cam_015',
        location: 'Main Entrance',
        dataType: 'security',
        privacyLevel: 'high',
        data: {
            motionDetected: true,
            personCount: 3,
            alertLevel: 'normal',
            timestamp: new Date().toISOString()
        }
    }
};

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupNavigation();
    setupEventListeners();
    startSystemMonitoring();
    setupQuickTestButtons();
});

// Initialize the application
function initializeApp() {
    console.log('🚀 Initializing Enhanced Hybrid Blockchain IoT System Frontend');
    
    updateSystemStatus();
    addLogEntry('INFO', 'Frontend interface initialized successfully');
    
    // Add welcome message
    showNotification('System Ready', 'Hybrid Blockchain IoT System is operational', 'success');
}

// Setup navigation
function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    const sections = document.querySelectorAll('.section');
    
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            
            navLinks.forEach(l => l.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));
            
            link.classList.add('active');
            
            const targetId = link.getAttribute('href').substring(1);
            const targetSection = document.getElementById(targetId);
            if (targetSection) {
                targetSection.classList.add('active');
                addLogEntry('INFO', `Navigated to ${targetId} section`);
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
    
    // Form preview updates
    const formInputs = document.querySelectorAll('#data-form input, #data-form select, #data-form textarea');
    formInputs.forEach(input => {
        input.addEventListener('input', updateDataPreview);
    });
}

// Setup quick test buttons
function setupQuickTestButtons() {
    // Add quick test buttons to the data ingestion form
    const formContainer = document.querySelector('.ingestion-form');
    if (formContainer && !document.getElementById('quick-test-buttons')) {
        const quickTestDiv = document.createElement('div');
        quickTestDiv.id = 'quick-test-buttons';
        quickTestDiv.className = 'quick-test-buttons';
        quickTestDiv.innerHTML = `
            <h4>Quick Test Data:</h4>
            <div class="button-group">
                <button type="button" class="btn btn-secondary btn-sm" onclick="loadSampleData('environmental')">
                    <i class="fas fa-cloud"></i> Environmental
                </button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="loadSampleData('medical')">
                    <i class="fas fa-heartbeat"></i> Medical
                </button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="loadSampleData('industrial')">
                    <i class="fas fa-industry"></i> Industrial
                </button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="loadSampleData('security')">
                    <i class="fas fa-shield-alt"></i> Security
                </button>
            </div>
        `;
        
        formContainer.insertBefore(quickTestDiv, formContainer.firstChild);
    }
}

// Load sample data into form
window.loadSampleData = function(type) {
    const sample = SAMPLE_DATA[type];
    if (!sample) return;
    
    document.getElementById('device-id').value = sample.deviceId;
    document.getElementById('location').value = sample.location;
    document.getElementById('data-type').value = sample.dataType;
    document.getElementById('privacy-level').value = sample.privacyLevel;
    document.getElementById('data-payload').value = JSON.stringify(sample.data, null, 2);
    
    updateDataPreview();
    showNotification('Sample Loaded', `${type} sample data loaded successfully`, 'info');
    addLogEntry('INFO', `Loaded ${type} sample data`);
};

// Start system monitoring
function startSystemMonitoring() {
    checkSystemHealth();
    setInterval(checkSystemHealth, CONFIG.REFRESH_INTERVAL);
    setInterval(updateSystemMetrics, 1000);
}

// Check system health
async function checkSystemHealth() {
    const services = [
        { name: 'orchestrator', url: `${CONFIG.ORCHESTRATOR_URL}/health`, key: 'orchestrator' },
        { name: 'mlGateway', url: `${CONFIG.ML_GATEWAY_URL}/health`, key: 'mlGateway' },
        { name: 'mlPrivacy', url: `${CONFIG.ML_PRIVACY_URL}/health`, key: 'mlPrivacy' }
    ];
    
    for (const service of services) {
        try {
            const response = await fetch(service.url, { method: 'GET' });
            
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
    
    await checkEthereumStatus();
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
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            systemState.ethereum = 'online';
            updateServiceStatus('ethereum', 'online');
            
            // Update block number
            const blockNumber = parseInt(data.result, 16);
            const blockElement = document.getElementById('eth-block-number');
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

// Update service status
function updateServiceStatus(service, status) {
    const statusMap = {
        orchestrator: 'orchestrator-status',
        mlGateway: 'ml-status',
        mlPrivacy: 'ml-status',
        ethereum: 'ethereum-status',
        fabric: 'fabric-status'
    };
    
    const elementId = statusMap[service];
    const element = document.getElementById(elementId);
    
    if (element) {
        element.textContent = status === 'online' ? 'Online' : 'Offline';
        element.className = `status-badge ${status}`;
    }
}

// Update system metrics
function updateSystemMetrics() {
    const now = new Date();
    const uptime = Math.floor((now - systemState.startTime) / 1000);
    
    const hours = Math.floor(uptime / 3600);
    const minutes = Math.floor((uptime % 3600) / 60);
    const seconds = uptime % 60;
    const uptimeString = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    
    const uptimeElement = document.getElementById('system-uptime');
    if (uptimeElement) uptimeElement.textContent = uptimeString;
    
    const dataProcessedElement = document.getElementById('data-processed');
    if (dataProcessedElement) dataProcessedElement.textContent = systemState.dataProcessed;
    
    const blockchainTxsElement = document.getElementById('blockchain-txs');
    if (blockchainTxsElement) blockchainTxsElement.textContent = systemState.blockchainTxs;
}

// Handle data submission
async function handleDataSubmission(e) {
    e.preventDefault();
    
    const deviceId = document.getElementById('device-id').value;
    const location = document.getElementById('location').value;
    const dataType = document.getElementById('data-type').value;
    const dataPayload = document.getElementById('data-payload').value;
    const privacyLevel = document.getElementById('privacy-level').value;
    
    let parsedData;
    try {
        parsedData = JSON.parse(dataPayload);
    } catch (error) {
        showNotification('Error', 'Invalid JSON format in data payload', 'error');
        return;
    }
    
    const submissionData = {
        id: `${deviceId}_${Date.now()}`,
        deviceId: deviceId,
        timestamp: new Date().toISOString(),
        location: location,
        dataType: dataType,
        privacyLevel: privacyLevel,
        data: parsedData
    };
    
    const submitButton = e.target.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    submitButton.disabled = true;
    
    try {
        const response = await fetch(`${CONFIG.ORCHESTRATOR_URL}/ingest_data`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(submissionData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            systemState.dataProcessed++;
            systemState.blockchainTxs++;
            
            // Add to recent transactions
            systemState.recentTransactions.unshift({
                id: submissionData.id,
                deviceId: deviceId,
                txHash: result.ethereum_tx_hash,
                timestamp: new Date().toISOString(),
                dataType: dataType
            });
            
            if (systemState.recentTransactions.length > 10) {
                systemState.recentTransactions.pop();
            }
            
            showSubmissionResults(true, result, submissionData);
            showNotification('Success', 'Data processed and stored on blockchain', 'success');
            addLogEntry('SUCCESS', `Data from ${deviceId} processed successfully`);
            
            updateRecentTransactions();
            e.target.reset();
            updateDataPreview();
        } else {
            showSubmissionResults(false, result, submissionData);
            showNotification('Error', result.message || 'Data submission failed', 'error');
            addLogEntry('ERROR', `Data submission failed: ${result.message}`);
        }
        
    } catch (error) {
        showNotification('Error', `Network error: ${error.message}`, 'error');
        addLogEntry('ERROR', `Network error: ${error.message}`);
    } finally {
        submitButton.innerHTML = originalText;
        submitButton.disabled = false;
    }
}

// Show submission results
function showSubmissionResults(success, result, data) {
    const resultsContainer = document.getElementById('results-container');
    const resultsContent = document.getElementById('results-content');
    
    if (!resultsContainer || !resultsContent) return;
    
    resultsContainer.style.display = 'block';
    
    if (success) {
        resultsContent.innerHTML = `
            <div class="result-success">
                <h4><i class="fas fa-check-circle"></i> Data Successfully Processed</h4>
                <div class="result-details">
                    <p><strong>Data ID:</strong> ${result.data_id || data.id}</p>
                    <p><strong>Device:</strong> ${data.deviceId}</p>
                    <p><strong>Ethereum TX:</strong> <code>${result.ethereum_tx_hash || 'N/A'}</code></p>
                    <p><strong>Fabric TX:</strong> <code>${result.fabric_tx_id || 'Stored'}</code></p>
                    <p><strong>Privacy Level:</strong> ${data.privacyLevel}</p>
                    <p><strong>Timestamp:</strong> ${new Date().toLocaleString()}</p>
                </div>
                <div class="result-actions">
                    <button class="btn btn-secondary btn-sm" onclick="viewOnEtherscan('${result.ethereum_tx_hash}')">
                        <i class="fas fa-external-link-alt"></i> View on Blockchain
                    </button>
                </div>
            </div>
        `;
    } else {
        resultsContent.innerHTML = `
            <div class="result-error">
                <h4><i class="fas fa-exclamation-circle"></i> Submission Failed</h4>
                <p>${result.message || 'Unknown error occurred'}</p>
            </div>
        `;
    }
}

// Update data preview
function updateDataPreview() {
    const previewContent = document.getElementById('preview-content');
    if (!previewContent) return;
    
    const deviceId = document.getElementById('device-id')?.value || '';
    const location = document.getElementById('location')?.value || '';
    const dataType = document.getElementById('data-type')?.value || '';
    const dataPayload = document.getElementById('data-payload')?.value || '';
    const privacyLevel = document.getElementById('privacy-level')?.value || '';
    
    let parsedData;
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
                    <strong>2. ML Privacy Filter</strong>
                    <p>Data Type: ${dataType || 'Not specified'}</p>
                    <p>Privacy Level: ${privacyLevel || 'Not specified'}</p>
                </div>
                <div class="preview-step">
                    <strong>3. Blockchain Storage</strong>
                    <p>Private: Full data → Hyperledger Fabric</p>
                    <p>Public: Metadata → Ethereum</p>
                </div>
            </div>
        </div>
        <div class="preview-section">
            <h4>📋 Data Payload:</h4>
            <pre>${JSON.stringify(parsedData, null, 2)}</pre>
        </div>
    `;
}

// Update recent transactions display
function updateRecentTransactions() {
    const txList = document.getElementById('recent-transactions-list');
    if (!txList) return;
    
    if (systemState.recentTransactions.length === 0) {
        txList.innerHTML = '<p class="no-data">No recent transactions</p>';
        return;
    }
    
    txList.innerHTML = systemState.recentTransactions.map(tx => `
        <div class="transaction-item">
            <div class="tx-icon"><i class="fas fa-cube"></i></div>
            <div class="tx-details">
                <div class="tx-id">${tx.id}</div>
                <div class="tx-meta">
                    <span class="tx-device">${tx.deviceId}</span>
                    <span class="tx-type">${tx.dataType}</span>
                    <span class="tx-time">${new Date(tx.timestamp).toLocaleTimeString()}</span>
                </div>
                <div class="tx-hash" title="${tx.txHash}">${tx.txHash.substring(0, 20)}...</div>
            </div>
        </div>
    `).join('');
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
    
    while (logsContent.children.length > 50) {
        logsContent.removeChild(logsContent.lastChild);
    }
}

// Show notification
function showNotification(title, message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <strong>${title}</strong>
            <p>${message}</p>
        </div>
        <button class="notification-close" onclick="this.parentElement.remove()">×</button>
    `;
    
    // Add to page
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        document.body.appendChild(container);
    }
    
    container.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// View on Etherscan (placeholder)
window.viewOnEtherscan = function(txHash) {
    showNotification('Info', `Transaction: ${txHash}`, 'info');
    addLogEntry('INFO', `Viewing transaction: ${txHash}`);
};

// Export functions for global access
window.loadSampleData = loadSampleData;
window.viewOnEtherscan = viewOnEtherscan;
