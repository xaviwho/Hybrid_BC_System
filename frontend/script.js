// System Configuration
const CONFIG = {
    ORCHESTRATOR_URL: 'http://localhost:5002',
    ML_GATEWAY_URL: 'http://localhost:5000',
    ML_PRIVACY_URL: 'http://localhost:5001',
    ETHEREUM_URL: 'http://localhost:8545',
    REFRESH_INTERVAL: 5000, // 5 seconds
    FABRIC_PEER_URL: 'localhost:7051',
    WEBSOCKET_URL: 'http://localhost:5002'
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

// WebSocket connection
let socket = null;
let activeTwins = {};
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

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
    setupFileUpload();
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
        
        let result;
        try {
            result = await response.json();
        } catch (e) {
            result = await response.text();
        }
        
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
            document.getElementById('file-preview-container').style.display = 'none';
            parsedFileData = null;
            updateDataPreview();
        } else {
            addLogEntry('ERROR', `Data submission failed: ${JSON.stringify(result)}`);
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
    
    // Parse response if it's an object
    let responseHTML = '';
    if (typeof message === 'object') {
        responseHTML = `
            <div class="response-details">
                ${message.message ? `<p><strong>Message:</strong> ${message.message}</p>` : ''}
                ${message.ethereum_tx_hash ? `<p><strong>Ethereum TX:</strong> <code>${message.ethereum_tx_hash}</code></p>` : ''}
                ${message.fabric_tx_id ? `<p><strong>Fabric TX:</strong> <code>${message.fabric_tx_id}</code></p>` : ''}
                ${message.sensitivity_level ? `<p><strong>Sensitivity:</strong> ${message.sensitivity_level}</p>` : ''}
                ${message.public_metadata ? `<p><strong>Public Metadata:</strong> <code>${JSON.stringify(message.public_metadata)}</code></p>` : ''}
            </div>
        `;
    } else {
        responseHTML = `<pre>${message}</pre>`;
    }
    
    resultsContent.innerHTML = `
        <div class="result-status ${statusClass}">
            <i class="${statusIcon}"></i>
            <span>${statusText}</span>
        </div>
        <div class="result-details">
            <h4>📋 Submission Details:</h4>
            <p><strong>Device ID:</strong> ${data.deviceId}</p>
            <p><strong>Timestamp:</strong> ${data.timestamp}</p>
            <p><strong>Location:</strong> ${data.location}</p>
            <p><strong>Data Type:</strong> ${data.dataType}</p>
            <p><strong>Privacy Level:</strong> ${data.privacyLevel}</p>
            <p><strong>Data Payload:</strong> <code>${JSON.stringify(data.data)}</code></p>
        </div>
        <div class="result-message">
            <h4>🔗 Blockchain Response:</h4>
            ${responseHTML}
        </div>
    `;
    
    // Auto-hide after 15 seconds
    setTimeout(() => {
        resultsContainer.style.display = 'none';
    }, 15000);
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
window.queryFabricData = async function() {
    addLogEntry('INFO', 'Querying Hyperledger Fabric data...');
    showNotification('Info', 'Querying Hyperledger Fabric blockchain...', 'info');
    
    try {
        // Try to query through orchestrator
        const response = await fetch(`${CONFIG.ORCHESTRATOR_URL}/fabric/query`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            const data = await response.json();
            showNotification('Success', `Fabric query successful. Found ${data.count || 0} records.`, 'success');
            addLogEntry('SUCCESS', 'Fabric data queried successfully');
        } else {
            showNotification('Info', 'Fabric query endpoint not yet implemented. This will query private blockchain data.', 'info');
            addLogEntry('INFO', 'Fabric query endpoint pending implementation');
        }
    } catch (error) {
        showNotification('Info', 'Fabric query feature: This would retrieve private data from Hyperledger Fabric blockchain.', 'info');
        addLogEntry('INFO', 'Fabric query feature demonstration');
    }
}

window.queryEthereumData = async function() {
    addLogEntry('INFO', 'Querying Ethereum registry...');
    showNotification('Info', 'Querying Ethereum public blockchain...', 'info');
    
    try {
        const response = await fetch(CONFIG.ETHEREUM_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'eth_getBlockByNumber',
                params: ['latest', false],
                id: 1
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            const blockNumber = parseInt(data.result.number, 16);
            showNotification('Success', `Ethereum is online. Current block: ${blockNumber}`, 'success');
            addLogEntry('SUCCESS', `Ethereum query successful: Block ${blockNumber}`);
        } else {
            showNotification('Error', 'Failed to query Ethereum', 'error');
            addLogEntry('ERROR', 'Ethereum query failed');
        }
    } catch (error) {
        showNotification('Error', `Ethereum query failed: ${error.message}`, 'error');
        addLogEntry('ERROR', `Ethereum query failed: ${error.message}`);
    }
}

// ML Service Testing Functions
window.testMLGateway = async function() {
    addLogEntry('INFO', 'Testing ML Gateway Filter...');
    showNotification('Testing', 'Testing ML Gateway Filter...', 'info');
    
    try {
        const response = await fetch(`${CONFIG.ML_GATEWAY_URL}/health`);
        if (response.ok) {
            const data = await response.json();
            showNotification('Success', `ML Gateway is online: ${data.status || 'healthy'}`, 'success');
            addLogEntry('SUCCESS', 'ML Gateway test completed successfully');
        } else {
            showNotification('Error', 'ML Gateway returned an error', 'error');
            addLogEntry('ERROR', 'ML Gateway test failed');
        }
    } catch (error) {
        showNotification('Error', `ML Gateway test failed: ${error.message}`, 'error');
        addLogEntry('ERROR', `ML Gateway test failed: ${error.message}`);
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
    showInfo(`${type.charAt(0).toUpperCase() + type.slice(1)} sample data loaded`);
    addLogEntry('INFO', `Loaded ${type} sample data`);
};

// Setup file upload functionality
function setupFileUpload() {
    const fileInput = document.getElementById('file-input');
    const fileUploadArea = document.getElementById('file-upload-area');
    
    if (!fileInput || !fileUploadArea) return;
    
    // Handle file selection
    fileInput.addEventListener('change', handleFileSelect);
    
    // Handle drag and drop
    fileUploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        fileUploadArea.classList.add('drag-over');
    });
    
    fileUploadArea.addEventListener('dragleave', () => {
        fileUploadArea.classList.remove('drag-over');
    });
    
    fileUploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        fileUploadArea.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });
}

// Handle file selection
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        handleFile(file);
    }
}

// Global variable to store parsed file data
let parsedFileData = null;
let currentPreviewMode = 'table';

// Handle file processing
function handleFile(file) {
    const fileExtension = file.name.split('.').pop().toLowerCase();
    const supportedFormats = ['json', 'csv', 'xlsx', 'xls'];
    
    if (!supportedFormats.includes(fileExtension)) {
        showError('Please upload a JSON, CSV, XLSX, or XLS file');
        return;
    }
    
    // Show file info
    document.querySelector('.upload-prompt').style.display = 'none';
    document.getElementById('file-info').style.display = 'flex';
    document.getElementById('file-name').textContent = file.name;
    
    // Parse based on file type
    if (fileExtension === 'json') {
        parseJSONFile(file);
    } else if (fileExtension === 'csv') {
        parseCSVFile(file);
    } else if (fileExtension === 'xlsx' || fileExtension === 'xls') {
        parseExcelFile(file);
    }
}

// Parse JSON file
function parseJSONFile(file) {
    const reader = new FileReader();
    
    reader.onload = function(e) {
        try {
            const jsonData = JSON.parse(e.target.result);
            parsedFileData = jsonData;
            
            // Populate form with file data
            populateFormFromData(jsonData);
            
            // Show preview
            showFilePreview(jsonData, 'json');
            
            showInfo(`JSON file "${file.name}" loaded successfully`);
            addLogEntry('INFO', `Loaded JSON file: ${file.name}`);
            
        } catch (error) {
            showError('Invalid JSON file format');
            addLogEntry('ERROR', `Failed to parse JSON file: ${error.message}`);
        }
    };
    
    reader.onerror = function() {
        showError('Failed to read file');
        addLogEntry('ERROR', 'File read error');
    };
    
    reader.readAsText(file);
}

// Parse CSV file
function parseCSVFile(file) {
    Papa.parse(file, {
        header: true,
        dynamicTyping: true,
        skipEmptyLines: true,
        complete: function(results) {
            parsedFileData = results.data;
            
            // Show preview
            showFilePreview(results.data, 'csv');
            
            showInfo(`CSV file "${file.name}" loaded successfully (${results.data.length} rows)`);
            addLogEntry('INFO', `Loaded CSV file: ${file.name} with ${results.data.length} rows`);
        },
        error: function(error) {
            showError(`Failed to parse CSV: ${error.message}`);
            addLogEntry('ERROR', `CSV parse error: ${error.message}`);
        }
    });
}

// Parse Excel file (XLSX/XLS)
function parseExcelFile(file) {
    const reader = new FileReader();
    
    reader.onload = function(e) {
        try {
            const data = new Uint8Array(e.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            
            // Get first sheet
            const firstSheetName = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[firstSheetName];
            
            // Convert to JSON
            const jsonData = XLSX.utils.sheet_to_json(worksheet);
            parsedFileData = jsonData;
            
            // Show preview
            showFilePreview(jsonData, 'excel');
            
            showInfo(`Excel file "${file.name}" loaded successfully (${jsonData.length} rows)`);
            addLogEntry('INFO', `Loaded Excel file: ${file.name} with ${jsonData.length} rows from sheet "${firstSheetName}"`);
            
        } catch (error) {
            showError(`Failed to parse Excel file: ${error.message}`);
            addLogEntry('ERROR', `Excel parse error: ${error.message}`);
        }
    };
    
    reader.onerror = function() {
        showError('Failed to read Excel file');
        addLogEntry('ERROR', 'Excel file read error');
    };
    
    reader.readAsArrayBuffer(file);
}

// Populate form from data
function populateFormFromData(data) {
    if (data.deviceId) document.getElementById('device-id').value = data.deviceId;
    if (data.location) document.getElementById('location').value = data.location;
    if (data.dataType) document.getElementById('data-type').value = data.dataType;
    if (data.privacyLevel) document.getElementById('privacy-level').value = data.privacyLevel;
    if (data.data) {
        document.getElementById('data-payload').value = JSON.stringify(data.data, null, 2);
    }
    updateDataPreview();
}

// Show file preview
function showFilePreview(data, fileType) {
    const previewContainer = document.getElementById('file-preview-container');
    const previewContent = document.getElementById('file-preview-content');
    const fileStats = document.getElementById('file-stats');
    
    previewContainer.style.display = 'block';
    
    // Generate preview based on current mode
    if (currentPreviewMode === 'table') {
        previewContent.innerHTML = generateTablePreview(data, fileType);
    } else {
        previewContent.innerHTML = generateJSONPreview(data);
    }
    
    // Show file statistics
    if (Array.isArray(data)) {
        const rowCount = data.length;
        const colCount = data.length > 0 ? Object.keys(data[0]).length : 0;
        fileStats.innerHTML = `
            <div class="stat-item">
                <i class="fas fa-table"></i> <strong>${rowCount}</strong> rows
            </div>
            <div class="stat-item">
                <i class="fas fa-columns"></i> <strong>${colCount}</strong> columns
            </div>
            <div class="stat-item">
                <i class="fas fa-file"></i> Type: <strong>${fileType.toUpperCase()}</strong>
            </div>
        `;
    } else {
        fileStats.innerHTML = `
            <div class="stat-item">
                <i class="fas fa-file"></i> Type: <strong>JSON Object</strong>
            </div>
        `;
    }
}

// Generate table preview
function generateTablePreview(data, fileType) {
    if (!Array.isArray(data)) {
        data = [data];
    }
    
    if (data.length === 0) {
        return '<p class="no-data">No data to preview</p>';
    }
    
    // Limit preview to first 10 rows
    const previewData = data.slice(0, 10);
    const columns = Object.keys(previewData[0]);
    
    let html = '<div class="table-wrapper"><table class="preview-table">';
    
    // Header
    html += '<thead><tr>';
    columns.forEach(col => {
        html += `<th>${col}</th>`;
    });
    html += '</tr></thead>';
    
    // Body
    html += '<tbody>';
    previewData.forEach(row => {
        html += '<tr>';
        columns.forEach(col => {
            const value = row[col];
            const displayValue = value !== null && value !== undefined ? value : '';
            html += `<td>${displayValue}</td>`;
        });
        html += '</tr>';
    });
    html += '</tbody>';
    
    html += '</table></div>';
    
    if (data.length > 10) {
        html += `<p class="preview-note"><i class="fas fa-info-circle"></i> Showing first 10 of ${data.length} rows</p>`;
    }
    
    return html;
}

// Generate JSON preview
function generateJSONPreview(data) {
    const previewData = Array.isArray(data) ? data.slice(0, 5) : data;
    
    let html = '<div class="json-preview-wrapper"><pre class="json-preview-code">';
    html += JSON.stringify(previewData, null, 2);
    html += '</pre></div>';
    
    if (Array.isArray(data) && data.length > 5) {
        html += `<p class="preview-note"><i class="fas fa-info-circle"></i> Showing first 5 of ${data.length} items</p>`;
    }
    
    return html;
}

// Toggle preview mode
window.togglePreviewMode = function(mode) {
    currentPreviewMode = mode;
    
    if (parsedFileData) {
        const previewContent = document.getElementById('file-preview-content');
        
        if (mode === 'table') {
            previewContent.innerHTML = generateTablePreview(parsedFileData, 'data');
        } else {
            previewContent.innerHTML = generateJSONPreview(parsedFileData);
        }
    }
    
    // Update button states
    document.querySelectorAll('.btn-preview-control').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.closest('.btn-preview-control').classList.add('active');
};

// Select data mapping (for CSV/Excel to JSON conversion)
window.selectDataMapping = function() {
    if (!parsedFileData || !Array.isArray(parsedFileData)) {
        showError('No tabular data loaded to map');
        return;
    }
    
    // Show mapping dialog
    showMappingDialog(parsedFileData);
};

// Show mapping dialog
function showMappingDialog(data) {
    const columns = Object.keys(data[0]);
    
    const dialogHTML = `
        <div class="mapping-dialog-overlay" onclick="closeMappingDialog()">
            <div class="mapping-dialog" onclick="event.stopPropagation()">
                <h3><i class="fas fa-map"></i> Map Columns to Digital Twin Data Format</h3>
                <p>Map your CSV/Excel columns to the required Digital Twin data fields:</p>
                
                <div class="mapping-form">
                    <div class="mapping-row">
                        <label>Timestamp Column:</label>
                        <select id="map-timestamp">
                            <option value="">-- Select Column --</option>
                            ${columns.map(col => `<option value="${col}">${col}</option>`).join('')}
                        </select>
                    </div>
                    
                    <div class="mapping-row">
                        <label>Device ID Column:</label>
                        <select id="map-deviceId">
                            <option value="">-- Select Column --</option>
                            ${columns.map(col => `<option value="${col}">${col}</option>`).join('')}
                        </select>
                    </div>
                    
                    <div class="mapping-row">
                        <label>Location Column (Optional):</label>
                        <select id="map-location">
                            <option value="">-- Select Column --</option>
                            ${columns.map(col => `<option value="${col}">${col}</option>`).join('')}
                        </select>
                    </div>
                    
                    <div class="mapping-row">
                        <label>Data Type:</label>
                        <select id="map-dataType">
                            <option value="medical">Medical</option>
                            <option value="environmental">Environmental</option>
                            <option value="industrial">Industrial</option>
                            <option value="manufacturing">Manufacturing</option>
                            <option value="security">Security</option>
                        </select>
                    </div>
                    
                    <div class="mapping-row">
                        <label>Privacy Level:</label>
                        <select id="map-privacyLevel">
                            <option value="high">High</option>
                            <option value="medium" selected>Medium</option>
                            <option value="low">Low</option>
                        </select>
                    </div>
                    
                    <p class="mapping-note">
                        <i class="fas fa-info-circle"></i> 
                        All other columns will be automatically included in the data payload
                    </p>
                    
                    <div class="mapping-preview">
                        <strong>Preview:</strong> First row will be used as example
                    </div>
                </div>
                
                <div class="mapping-actions">
                    <button class="btn btn-secondary" onclick="closeMappingDialog()">Cancel</button>
                    <button class="btn btn-primary" onclick="applyMapping()">Apply Mapping</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', dialogHTML);
}

// Close mapping dialog
window.closeMappingDialog = function() {
    const dialog = document.querySelector('.mapping-dialog-overlay');
    if (dialog) dialog.remove();
};

// Apply mapping
window.applyMapping = function() {
    const timestampCol = document.getElementById('map-timestamp').value;
    const deviceIdCol = document.getElementById('map-deviceId').value;
    const locationCol = document.getElementById('map-location').value;
    const dataType = document.getElementById('map-dataType').value;
    const privacyLevel = document.getElementById('map-privacyLevel').value;
    
    if (!deviceIdCol) {
        showError('Please select a Device ID column');
        return;
    }
    
    // Use first row as example
    const firstRow = parsedFileData[0];
    
    // Create mapped data
    const mappedData = {
        deviceId: firstRow[deviceIdCol] || 'device_001',
        location: locationCol ? firstRow[locationCol] : 'Not specified',
        dataType: dataType,
        privacyLevel: privacyLevel,
        timestamp: timestampCol ? firstRow[timestampCol] : new Date().toISOString(),
        data: {}
    };
    
    // Add all other columns to data payload
    Object.keys(firstRow).forEach(key => {
        if (key !== deviceIdCol && key !== locationCol && key !== timestampCol) {
            mappedData.data[key] = firstRow[key];
        }
    });
    
    // Populate form
    populateFormFromData(mappedData);
    
    closeMappingDialog();
    showInfo(`Column mapping applied: ${Object.keys(mappedData.data).length} data fields mapped`);
    addLogEntry('INFO', `Applied column mapping for ${dataType} data: ${Object.keys(mappedData.data).length} fields`);
};

// Clear uploaded file
window.clearFile = function() {
    document.getElementById('file-input').value = '';
    document.querySelector('.upload-prompt').style.display = 'block';
    document.getElementById('file-info').style.display = 'none';
    document.getElementById('file-preview-container').style.display = 'none';
    parsedFileData = null;
    showInfo('File cleared');
};

// Validate JSON
window.validateJSON = function() {
    const payload = document.getElementById('data-payload').value;
    const statusDiv = document.getElementById('json-status');
    
    try {
        JSON.parse(payload);
        statusDiv.innerHTML = '<span style="color: #10b981;"><i class="fas fa-check-circle"></i> Valid JSON</span>';
        setTimeout(() => statusDiv.innerHTML = '', 3000);
    } catch (error) {
        statusDiv.innerHTML = `<span style="color: #ef4444;"><i class="fas fa-exclamation-circle"></i> Invalid JSON: ${error.message}</span>`;
    }
};

// Update data preview with enhanced visualization
function updateDataPreview() {
    const previewContent = document.getElementById('preview-content');
    if (!previewContent) return;
    
    const deviceId = document.getElementById('device-id')?.value || '';
    const location = document.getElementById('location')?.value || '';
    const dataType = document.getElementById('data-type')?.value || '';
    const dataPayload = document.getElementById('data-payload')?.value || '';
    const privacyLevel = document.getElementById('privacy-level')?.value || '';
    
    let parsedData;
    let isValidJSON = false;
    try {
        if (dataPayload) {
            parsedData = JSON.parse(dataPayload);
            isValidJSON = true;
        }
    } catch (error) {
        parsedData = { error: 'Invalid JSON format' };
    }
    
    const privacyIcon = privacyLevel === 'high' ? '🔒' : privacyLevel === 'medium' ? '🔐' : '🔓';
    const dataTypeIcon = dataType === 'medical' ? '❤️' : dataType === 'environmental' ? '🌡️' : dataType === 'industrial' ? '🏭' : '🔒';
    
    previewContent.innerHTML = `
        <div class="preview-header">
            <h4>Data Processing Flow Preview</h4>
        </div>
        
        <div class="preview-flow">
            <div class="preview-step">
                <div class="step-number">1</div>
                <strong>Data Ingestion</strong>
                <p>Device: ${deviceId || 'Not specified'}</p>
                <p>Location: ${location || 'Not specified'}</p>
            </div>
            
            <div class="preview-arrow">→</div>
            
            <div class="preview-step">
                <div class="step-number">2</div>
                <strong>ML Privacy Filter</strong>
                <p>Type: ${dataType || 'Not specified'}</p>
                <p>Privacy: ${privacyLevel || 'Not specified'}</p>
            </div>
            
            <div class="preview-arrow">→</div>
            
            <div class="preview-step">
                <div class="step-number">3</div>
                <strong>Blockchain Storage</strong>
                <p>Private: Full data → Fabric</p>
                <p>Public: Metadata → Ethereum</p>
            </div>
        </div>
        
        <div class="preview-data">
            <h4>Data Payload:</h4>
            <div class="json-preview ${isValidJSON ? 'valid' : 'invalid'}">
                <pre>${JSON.stringify(parsedData, null, 2)}</pre>
            </div>
            ${isValidJSON ? '<p class="preview-note">Sensitive fields will be automatically detected and protected</p>' : ''}
        </div>
    `;
}

// Helper functions for notifications
function showInfo(message) {
    showNotification('Info', message, 'info');
}

function showError(message) {
    showNotification('Error', message, 'error');
}

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

window.testMLPrivacy = async function() {
    addLogEntry('INFO', 'Testing ML Privacy Filter...');
    showNotification('Testing', 'Testing ML Privacy Filter...', 'info');
    
    try {
        const response = await fetch(`${CONFIG.ML_PRIVACY_URL}/health`);
        if (response.ok) {
            const data = await response.json();
            showNotification('Success', `ML Privacy Filter is online: ${data.status || 'healthy'}`, 'success');
            addLogEntry('SUCCESS', 'ML Privacy Filter test completed successfully');
        } else {
            showNotification('Error', 'ML Privacy Filter returned an error', 'error');
            addLogEntry('ERROR', 'ML Privacy Filter test failed');
        }
    } catch (error) {
        showNotification('Error', `ML Privacy Filter test failed: ${error.message}`, 'error');
        addLogEntry('ERROR', `ML Privacy Filter test failed: ${error.message}`);
    }
}

// View logs functions
window.viewFabricLogs = function() {
    addLogEntry('INFO', 'Viewing Hyperledger Fabric logs...');
    showNotification('Info', 'Fabric Logs: This feature displays transaction logs from the private blockchain. Check the System Status tab for recent activity.', 'info');
}

window.viewEthereumLogs = function() {
    addLogEntry('INFO', 'Viewing Ethereum logs...');
    showNotification('Info', 'Ethereum Logs: This feature displays transaction logs from the public blockchain. Check the System Status tab for recent activity.', 'info');
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

// Functions are already exported as window.functionName above

// Blockchain Data Explorer Functions
let blockchainDataCache = [];

// Search blockchain data
window.searchBlockchainData = async function() {
    const searchTerm = document.getElementById('tx-search').value.trim();
    const resultsDiv = document.getElementById('explorer-results');
    const contentDiv = document.getElementById('explorer-content');
    
    if (!searchTerm) {
        showNotification('Info', 'Please enter a transaction hash or device ID to search', 'info');
        return;
    }
    
    resultsDiv.style.display = 'block';
    contentDiv.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Searching blockchains...</div>';
    
    try {
        // Search in Ethereum
        const ethResult = await searchEthereum(searchTerm);
        
        // Display results
        if (ethResult) {
            displaySearchResults(ethResult, searchTerm);
        } else {
            contentDiv.innerHTML = `
                <div class="no-results">
                    <i class="fas fa-search"></i>
                    <p>No results found for "${searchTerm}"</p>
                    <p class="hint">Try searching for a transaction hash or device ID from your submissions</p>
                </div>
            `;
        }
    } catch (error) {
        contentDiv.innerHTML = `
            <div class="error-message">
                <i class="fas fa-exclamation-circle"></i>
                <p>Error searching blockchain: ${error.message}</p>
            </div>
        `;
    }
};

// Search Ethereum blockchain
async function searchEthereum(searchTerm) {
    try {
        // Try to get transaction by hash
        const response = await fetch(CONFIG.ETHEREUM_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'eth_getTransactionByHash',
                params: [searchTerm],
                id: 1
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.result) {
                return {
                    type: 'ethereum',
                    transaction: data.result,
                    searchTerm: searchTerm
                };
            }
        }
    } catch (error) {
        console.error('Ethereum search error:', error);
    }
    
    return null;
}

// Display search results
function displaySearchResults(result, searchTerm) {
    const contentDiv = document.getElementById('explorer-content');
    
    if (result.type === 'ethereum') {
        const tx = result.transaction;
        const blockNumber = tx.blockNumber ? parseInt(tx.blockNumber, 16) : 'Pending';
        const value = tx.value ? parseInt(tx.value, 16) : 0;
        
        contentDiv.innerHTML = `
            <div class="blockchain-result ethereum-result">
                <div class="result-header">
                    <i class="fab fa-ethereum"></i>
                    <h4>Ethereum Transaction Found</h4>
                    <span class="badge badge-success">Public Blockchain</span>
                </div>
                
                <div class="result-details">
                    <div class="detail-row">
                        <strong>Transaction Hash:</strong>
                        <code class="hash-display">${tx.hash}</code>
                    </div>
                    <div class="detail-row">
                        <strong>Block Number:</strong>
                        <span>${blockNumber}</span>
                    </div>
                    <div class="detail-row">
                        <strong>From:</strong>
                        <code>${tx.from}</code>
                    </div>
                    <div class="detail-row">
                        <strong>To (Contract):</strong>
                        <code>${tx.to}</code>
                    </div>
                    <div class="detail-row">
                        <strong>Gas Used:</strong>
                        <span>${tx.gas ? parseInt(tx.gas, 16) : 'N/A'}</span>
                    </div>
                    <div class="detail-row">
                        <strong>Input Data:</strong>
                        <code class="input-data">${tx.input.substring(0, 100)}${tx.input.length > 100 ? '...' : ''}</code>
                    </div>
                </div>
                
                <div class="result-explanation">
                    <h5><i class="fas fa-info-circle"></i> What This Means:</h5>
                    <ul>
                        <li><strong>Public Record:</strong> This transaction is visible to everyone on Ethereum</li>
                        <li><strong>Metadata Only:</strong> Contains device info, timestamp, and hash - NO sensitive data</li>
                        <li><strong>Immutable:</strong> Cannot be changed or deleted</li>
                        <li><strong>Verifiable:</strong> Anyone can verify this data exists</li>
                    </ul>
                </div>
                
                <div class="result-actions">
                    <button class="btn btn-outline" onclick="decodeTransactionData('${tx.input}')">
                        <i class="fas fa-code"></i> Decode Data
                    </button>
                    <button class="btn btn-outline" onclick="viewOnEtherscan('${tx.hash}')">
                        <i class="fas fa-external-link-alt"></i> View on Etherscan
                    </button>
                </div>
            </div>
        `;
    }
}

// View all transactions
window.viewAllTransactions = async function() {
    const resultsDiv = document.getElementById('explorer-results');
    const contentDiv = document.getElementById('explorer-content');
    
    resultsDiv.style.display = 'block';
    contentDiv.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Loading recent transactions...</div>';
    
    try {
        // Get recent blocks and transactions
        const recentTxs = await getRecentTransactions();
        
        if (recentTxs && recentTxs.length > 0) {
            displayAllTransactions(recentTxs);
        } else {
            contentDiv.innerHTML = `
                <div class="no-results">
                    <i class="fas fa-inbox"></i>
                    <p>No transactions found yet</p>
                    <p class="hint">Submit some data first to see transactions here</p>
                </div>
            `;
        }
    } catch (error) {
        contentDiv.innerHTML = `
            <div class="error-message">
                <i class="fas fa-exclamation-circle"></i>
                <p>Error loading transactions: ${error.message}</p>
            </div>
        `;
    }
};

// Get recent transactions
async function getRecentTransactions() {
    try {
        // Get latest block
        const blockResponse = await fetch(CONFIG.ETHEREUM_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'eth_getBlockByNumber',
                params: ['latest', true],
                id: 1
            })
        });
        
        if (blockResponse.ok) {
            const blockData = await blockResponse.json();
            if (blockData.result && blockData.result.transactions) {
                return blockData.result.transactions.slice(0, 10); // Last 10 transactions
            }
        }
    } catch (error) {
        console.error('Error getting recent transactions:', error);
    }
    
    return [];
}

// Display all transactions
function displayAllTransactions(transactions) {
    const contentDiv = document.getElementById('explorer-content');
    
    let html = '<div class="transactions-list">';
    
    transactions.forEach((tx, index) => {
        const blockNumber = tx.blockNumber ? parseInt(tx.blockNumber, 16) : 'Pending';
        
        html += `
            <div class="transaction-item">
                <div class="tx-header">
                    <span class="tx-number">#${index + 1}</span>
                    <code class="tx-hash">${tx.hash.substring(0, 20)}...${tx.hash.substring(tx.hash.length - 10)}</code>
                    <span class="tx-block">Block ${blockNumber}</span>
                </div>
                <div class="tx-details">
                    <span><strong>From:</strong> ${tx.from.substring(0, 10)}...${tx.from.substring(tx.from.length - 8)}</span>
                    <span><strong>To:</strong> ${tx.to ? tx.to.substring(0, 10) + '...' + tx.to.substring(tx.to.length - 8) : 'Contract Creation'}</span>
                </div>
                <button class="btn-small" onclick="searchBlockchainData(); document.getElementById('tx-search').value='${tx.hash}'">
                    <i class="fas fa-eye"></i> View Details
                </button>
            </div>
        `;
    });
    
    html += '</div>';
    
    html += `
        <div class="transactions-summary">
            <p><i class="fas fa-info-circle"></i> Showing ${transactions.length} most recent transactions</p>
            <p>Each transaction represents data registered on the public Ethereum blockchain</p>
        </div>
    `;
    
    contentDiv.innerHTML = html;
}

// Smart Contract ABI for IoTDataRegistry
const IOT_DATA_REGISTRY_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "_dataId", "type": "bytes32"},
            {"internalType": "string", "name": "_dataHash", "type": "string"},
            {"internalType": "string", "name": "_metadata", "type": "string"}
        ],
        "name": "registerData",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "anonymous": false,
        "inputs": [
            {"indexed": true, "internalType": "bytes32", "name": "id", "type": "bytes32"},
            {"indexed": true, "internalType": "address", "name": "owner", "type": "address"},
            {"indexed": false, "internalType": "string", "name": "dataHash", "type": "string"},
            {"indexed": false, "internalType": "uint256", "name": "registrationTime", "type": "uint256"}
        ],
        "name": "DataRegistered",
        "type": "event"
    }
];

// Decode transaction data using REAL ABI (NO MOCK DATA!)
window.decodeTransactionData = async function(inputData) {
    try {
        // Create interface from ABI
        const iface = new ethers.utils.Interface(IOT_DATA_REGISTRY_ABI);
        
        // Decode the transaction input
        const decodedData = iface.parseTransaction({ data: inputData });
        
        // Extract the REAL parameters
        const dataId = decodedData.args._dataId;
        const dataHash = decodedData.args._dataHash;
        const metadata = decodedData.args._metadata;
        
        // Parse metadata JSON if it's a JSON string
        let metadataObj = null;
        try {
            metadataObj = JSON.parse(metadata);
        } catch (e) {
            metadataObj = { raw: metadata };
        }
        
        // Show decoding modal with REAL DATA
        const modalHTML = `
            <div class="decode-modal-overlay" onclick="closeDecodeModal()">
                <div class="decode-modal" onclick="event.stopPropagation()">
                    <div class="decode-header">
                        <h3>Decoded Transaction Data</h3>
                        <button class="close-btn" onclick="closeDecodeModal()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    
                    <div class="decode-content">
                        <div class="decode-section">
                            <h4>Successfully Decoded Using Smart Contract ABI</h4>
                            <div class="success-box">
                                <p>Decoded using the IoTDataRegistry smart contract ABI.</p>
                            </div>
                        </div>
                        
                        <div class="decode-section">
                            <h4>Function Called:</h4>
                            <div class="function-box">
                                <code class="function-name">registerData(bytes32 _dataId, string _dataHash, string _metadata)</code>
                                <p>This function registers IoT data metadata on the public Ethereum blockchain.</p>
                            </div>
                        </div>
                        
                        <div class="decode-section">
                            <h4>Decoded Parameters:</h4>
                            <div class="params-container">
                                <div class="param-box">
                                    <div class="param-header">
                                        <span class="param-name">Parameter 1: _dataId</span>
                                        <span class="param-type">bytes32</span>
                                    </div>
                                    <div class="param-value-box">
                                        <code>${dataId}</code>
                                    </div>
                                    <p class="param-desc">Unique identifier for this data record on the blockchain</p>
                                </div>
                                
                                <div class="param-box">
                                    <div class="param-header">
                                        <span class="param-name">Parameter 2: _dataHash</span>
                                        <span class="param-type">string</span>
                                    </div>
                                    <div class="param-value-box">
                                        <code>${dataHash}</code>
                                    </div>
                                    <p class="param-desc">Cryptographic hash of the full data stored on Hyperledger Fabric</p>
                                </div>
                                
                                <div class="param-box">
                                    <div class="param-header">
                                        <span class="param-name">Parameter 3: _metadata</span>
                                        <span class="param-type">string (JSON)</span>
                                    </div>
                                    <div class="param-value-box">
                                        <pre class="metadata-json">${JSON.stringify(metadataObj, null, 2)}</pre>
                                    </div>
                                    <p class="param-desc">Public metadata (device info, timestamp) - NO sensitive data</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="decode-section">
                            <h4>Privacy Verification:</h4>
                            <div class="privacy-check">
                                ${checkPrivacy(metadata, metadataObj)}
                            </div>
                        </div>
                        
                        <div class="decode-section">
                            <h4>What This Means:</h4>
                            <div class="info-box">
                                <ul>
                                    <li><strong>Public Record:</strong> This transaction is permanently recorded on Ethereum</li>
                                    <li><strong>Metadata Only:</strong> Only non-sensitive metadata is public</li>
                                    <li><strong>Data Hash:</strong> Proves the full data exists and hasn't been tampered with</li>
                                    <li><strong>Fabric Reference:</strong> The full sensitive data is stored privately on Hyperledger Fabric</li>
                                    <li><strong>Immutable:</strong> This record cannot be changed or deleted</li>
                                </ul>
                            </div>
                        </div>
                        
                        <div class="decode-section">
                            <h4>Raw Input Data:</h4>
                            <div class="code-block">
                                <code>${inputData}</code>
                            </div>
                        </div>
                    </div>
                    
                    <div class="decode-actions">
                        <button class="btn btn-secondary" onclick="copyToClipboard('${inputData}')">
                            <i class="fas fa-copy"></i> Copy Raw Data
                        </button>
                        <button class="btn btn-secondary" onclick="copyToClipboard('${JSON.stringify(metadataObj, null, 2)}')">
                            <i class="fas fa-copy"></i> Copy Metadata
                        </button>
                        <button class="btn btn-primary" onclick="closeDecodeModal()">
                            <i class="fas fa-check"></i> Close
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        addLogEntry('SUCCESS', 'Successfully decoded transaction data using smart contract ABI');
        
    } catch (error) {
        console.error('Decode error:', error);
        showNotification('Error', `Failed to decode transaction: ${error.message}`, 'error');
        addLogEntry('ERROR', `Failed to decode transaction: ${error.message}`);
    }
};

// Check privacy - scan for sensitive data patterns
function checkPrivacy(metadataString, metadataObj) {
    const sensitivePatterns = {
        patientId: /patient.*id|p\d{5,}/i,
        ssn: /\d{3}-\d{2}-\d{4}/,
        email: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/,
        phone: /\d{3}[-.]?\d{3}[-.]?\d{4}/,
        creditCard: /\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}/,
        diagnosis: /diagnosis|condition|disease/i,
        prescription: /prescription|medication|drug/i
    };
    
    let checks = [];
    const dataToCheck = metadataString + JSON.stringify(metadataObj);
    
    // Check for patient IDs
    if (sensitivePatterns.patientId.test(dataToCheck)) {
        checks.push({ type: 'warning', message: 'Patient ID pattern detected' });
    } else {
        checks.push({ type: 'success', message: 'No patient IDs found' });
    }
    
    // Check for SSN
    if (sensitivePatterns.ssn.test(dataToCheck)) {
        checks.push({ type: 'warning', message: 'SSN pattern detected' });
    } else {
        checks.push({ type: 'success', message: 'No SSN found' });
    }
    
    // Check for email
    if (sensitivePatterns.email.test(dataToCheck)) {
        checks.push({ type: 'warning', message: 'Email address detected' });
    } else {
        checks.push({ type: 'success', message: 'No email addresses found' });
    }
    
    // Check for medical info
    if (sensitivePatterns.diagnosis.test(dataToCheck) || sensitivePatterns.prescription.test(dataToCheck)) {
        checks.push({ type: 'warning', message: 'Medical information detected' });
    } else {
        checks.push({ type: 'success', message: 'No medical information found' });
    }
    
    let html = '';
    checks.forEach(check => {
        const icon = check.type === 'success' ? 'fa-check-circle' : 'fa-exclamation-triangle';
        html += `
            <div class="check-item ${check.type}">
                <i class="fas ${icon}"></i>
                <span>${check.message}</span>
            </div>
        `;
    });
    
    return html;
}

// Close decode modal
window.closeDecodeModal = function() {
    const modal = document.querySelector('.decode-modal-overlay');
    if (modal) modal.remove();
};

// Copy to clipboard
window.copyToClipboard = function(text) {
    navigator.clipboard.writeText(text).then(() => {
        showNotification('Success', 'Copied to clipboard!', 'success');
    }).catch(err => {
        showNotification('Error', 'Failed to copy', 'error');
    });
};

// View on Etherscan
window.viewOnEtherscan = function(txHash) {
    showNotification('Info', 'In production, this would open Etherscan.io to view the transaction publicly', 'info');
    console.log('Transaction hash:', txHash);
    // window.open(`https://etherscan.io/tx/${txHash}`, '_blank');
};

// ===== REAL-TIME WEBSOCKET FUNCTIONALITY =====

function initializeWebSocket() {
    console.log('Initializing WebSocket connection...');
    
    try {
        socket = io(CONFIG.WEBSOCKET_URL, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionAttempts: MAX_RECONNECT_ATTEMPTS
        });

        // Connection established
        socket.on('connect', () => {
            console.log('WebSocket connected');
            reconnectAttempts = 0;
            updateConnectionStatus('connected');
            addStreamLog('Connected to real-time twin updates', 'success');
        });

        // Connection status update
        socket.on('connection_status', (data) => {
            console.log('Connection status:', data);
            addStreamLog(data.message, 'info');
        });

        // Active twins list
        socket.on('active_twins', (data) => {
            console.log('Active twins:', data);
            updateActiveTwinsCount(data.count);
            loadActiveTwins();
        });

        // Real-time twin update
        socket.on('twin_update', (data) => {
            console.log('Twin update received:', data);
            updateTwinCard(data.twin_id, data.data, data.timestamp);
            addStreamLog(`Update from ${data.twin_id}`, 'update');
        });

        // Twin state
        socket.on('twin_state', (data) => {
            console.log('Twin state:', data);
            activeTwins[data.twin_id] = data.state;
            renderTwinsGrid();
        });

        // Subscription confirmed
        socket.on('subscription_confirmed', (data) => {
            console.log('Subscription:', data);
            addStreamLog(`${data.status} to ${data.twin_id}`, 'info');
        });

        // Disconnection
        socket.on('disconnect', (reason) => {
            console.log('WebSocket disconnected:', reason);
            updateConnectionStatus('disconnected');
            addStreamLog('Disconnected from server', 'error');
            
            if (reason === 'io server disconnect') {
                // Server disconnected, try to reconnect
                socket.connect();
            }
        });

        // Connection error
        socket.on('connect_error', (error) => {
            console.error('WebSocket connection error:', error);
            reconnectAttempts++;
            
            if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
                updateConnectionStatus('failed');
                addStreamLog('Connection failed. Please check if orchestrator is running.', 'error');
            } else {
                updateConnectionStatus('reconnecting');
                addStreamLog(`Reconnecting... (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`, 'warning');
            }
        });

        // Reconnection attempt
        socket.on('reconnect_attempt', () => {
            console.log('Attempting to reconnect...');
            updateConnectionStatus('reconnecting');
        });

        // Reconnected
        socket.on('reconnect', () => {
            console.log('Reconnected successfully');
            reconnectAttempts = 0;
            updateConnectionStatus('connected');
            addStreamLog('Reconnected successfully', 'success');
            loadActiveTwins();
        });

    } catch (error) {
        console.error('Failed to initialize WebSocket:', error);
        updateConnectionStatus('failed');
        addStreamLog('Failed to initialize WebSocket connection', 'error');
    }
}

function updateConnectionStatus(status) {
    const statusIndicator = document.getElementById('ws-status');
    if (!statusIndicator) return;

    const dot = statusIndicator.querySelector('.status-dot');
    const text = statusIndicator.querySelector('.status-text');

    dot.className = 'status-dot';
    
    switch(status) {
        case 'connected':
            dot.classList.add('connected');
            text.textContent = 'Connected';
            break;
        case 'disconnected':
            dot.classList.add('disconnected');
            text.textContent = 'Disconnected';
            break;
        case 'reconnecting':
            dot.classList.add('reconnecting');
            text.textContent = 'Reconnecting...';
            break;
        case 'failed':
            dot.classList.add('disconnected');
            text.textContent = 'Connection Failed';
            break;
    }
}

function updateActiveTwinsCount(count) {
    const countElement = document.getElementById('active-twins-count');
    if (countElement) {
        countElement.textContent = `${count} Active Twin${count !== 1 ? 's' : ''}`;
    }
}

async function loadActiveTwins() {
    try {
        const response = await fetch(`${CONFIG.ORCHESTRATOR_URL}/twins`);
        if (response.ok) {
            const data = await response.json();
            activeTwins = data.twins;
            updateActiveTwinsCount(data.count);
            
            const clientsElement = document.getElementById('connected-clients');
            if (clientsElement) {
                clientsElement.textContent = `${data.connected_clients} Connected Client${data.connected_clients !== 1 ? 's' : ''}`;
            }
            
            renderTwinsGrid();
        }
    } catch (error) {
        console.error('Failed to load active twins:', error);
    }
}

function renderTwinsGrid() {
    const grid = document.getElementById('twins-grid');
    if (!grid) return;

    const twinIds = Object.keys(activeTwins);
    
    if (twinIds.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-cube"></i>
                <p>No active digital twins</p>
                <small>Submit data or stream real-time updates to see twins here</small>
            </div>
        `;
        return;
    }

    grid.innerHTML = twinIds.map(twinId => {
        const twin = activeTwins[twinId];
        const data = twin.data || {};
        const lastUpdate = new Date(twin.last_update).toLocaleTimeString();
        
        return `
            <div class="twin-card" id="twin-${twinId}">
                <div class="twin-header">
                    <div class="twin-icon">
                        <i class="fas fa-cube"></i>
                    </div>
                    <div class="twin-info">
                        <h4>${twinId}</h4>
                        <span class="twin-status ${twin.status}">${twin.status}</span>
                    </div>
                </div>
                <div class="twin-data">
                    ${renderTwinData(data)}
                </div>
                <div class="twin-footer">
                    <span class="last-update">Last update: ${lastUpdate}</span>
                </div>
            </div>
        `;
    }).join('');
}

function renderTwinData(data) {
    const keys = Object.keys(data).filter(k => !['deviceId', 'id', 'timestamp'].includes(k));
    
    if (keys.length === 0) return '<p class="no-data">No data available</p>';
    
    return keys.slice(0, 4).map(key => {
        let value = data[key];
        if (typeof value === 'object') value = JSON.stringify(value);
        if (typeof value === 'number') value = value.toFixed(2);
        
        return `
            <div class="data-row">
                <span class="data-label">${key}:</span>
                <span class="data-value">${value}</span>
            </div>
        `;
    }).join('');
}

function updateTwinCard(twinId, data, timestamp) {
    // Update in memory
    activeTwins[twinId] = {
        data: data,
        last_update: timestamp,
        status: 'active'
    };
    
    // Re-render grid
    renderTwinsGrid();
    
    // Update count
    updateActiveTwinsCount(Object.keys(activeTwins).length);
}

function addStreamLog(message, type = 'info') {
    const streamLog = document.getElementById('stream-log');
    if (!streamLog) return;

    const time = new Date().toLocaleTimeString();
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    logEntry.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-message">${message}</span>
    `;

    // Add to top
    streamLog.insertBefore(logEntry, streamLog.firstChild);

    // Keep only last 50 entries
    while (streamLog.children.length > 50) {
        streamLog.removeChild(streamLog.lastChild);
    }
}

function subscribeTwin(twinId) {
    if (socket && socket.connected) {
        socket.emit('subscribe_twin', { twin_id: twinId });
    }
}

function unsubscribeTwin(twinId) {
    if (socket && socket.connected) {
        socket.emit('unsubscribe_twin', { twin_id: twinId });
    }
}

// Initialize WebSocket when page loads
document.addEventListener('DOMContentLoaded', () => {
    initializeWebSocket();
    
    // Refresh active twins every 10 seconds
    setInterval(loadActiveTwins, 10000);
});
