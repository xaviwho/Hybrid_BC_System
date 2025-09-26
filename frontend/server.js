const express = require('express');
const path = require('path');
const cors = require('cors');

const app = express();
const PORT = 8080;

// Enable CORS for all routes
app.use(cors());

// Serve static files from the frontend directory
app.use(express.static(path.join(__dirname)));

// Serve the main HTML file
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({ 
        message: 'Frontend server is running', 
        status: 'ok',
        timestamp: new Date().toISOString()
    });
});

// Start the server
app.listen(PORT, () => {
    console.log(`🎨 Frontend server running at http://localhost:${PORT}`);
    console.log(`📊 Access your Hybrid Blockchain IoT Dashboard at:`);
    console.log(`   → http://localhost:${PORT}`);
    console.log(`\n🔗 System Integration:`);
    console.log(`   → Orchestrator API: http://localhost:5002`);
    console.log(`   → ML Gateway Filter: http://localhost:5000`);
    console.log(`   → ML Privacy Filter: http://localhost:5001`);
    console.log(`   → Ethereum Node: http://localhost:8545`);
    console.log(`   → Hyperledger Fabric: localhost:7051`);
});

module.exports = app;
