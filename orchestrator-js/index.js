const express = require('express');
const { Gateway, Wallets } = require('fabric-network');
const fs = require('fs');
const path = require('path');

const app = express();
const port = 3000;

// Enable CORS for frontend requests
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization');
    if (req.method === 'OPTIONS') {
        res.sendStatus(200);
    } else {
        next();
    }
});

app.use(express.json());

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({ message: 'Orchestrator service is running', status: 'ok' });
});

// Placeholder for the main data ingestion logic
app.post('/ingest_data', async (req, res) => {
    console.log('Received data for ingestion:', req.body);

    try {
        // TODO: Add ML service call
        // TODO: Add Ethereum contract call

        // --- Hyperledger Fabric Interaction ---
        const ccpPath = path.resolve(__dirname, 'connection-org1.json');
        const ccp = JSON.parse(fs.readFileSync(ccpPath, 'utf8'));

        // Create a new file system based wallet for managing identities.
        const walletPath = path.join(process.cwd(), 'wallet');
        const wallet = await Wallets.newFileSystemWallet(walletPath);
        console.log(`Wallet path: ${walletPath}`);

        // Check to see if we have the user identity in the wallet.
        const identity = await wallet.get('appUser');
        if (!identity) {
            console.log('An identity for the user "appUser" does not exist in the wallet');
            console.log('Run the enrollAdmin.js and registerUser.js applications before retrying');
            return res.status(500).send('User identity not found in wallet.');
        }

        // Create a new gateway for connecting to our peer node.
        const gateway = new Gateway();
        await gateway.connect(ccp, { wallet, identity: 'appUser', discovery: { enabled: true, asLocalhost: true } });

        // DEMO MODE: Mock chaincode response for demonstration
        // In production, this would connect to the actual Fabric network
        console.log(' [DEMO MODE] Simulating Fabric chaincode transaction...');

        // Extract deviceId properly from the data
        const deviceId = req.body.deviceId || req.body.id;
        if (!deviceId) {
            throw new Error('Missing deviceId in IoT data');
        }

        // Structure the IoT data properly
        const iotData = {
            id: deviceId,
            deviceId: deviceId,
            timestamp: req.body.timestamp || new Date().toISOString(),
            location: req.body.location || 'unknown',
            dataType: req.body.dataType || 'general',
            privacyLevel: req.body.privacyLevel || 'medium',
            data: JSON.stringify(req.body.data || req.body)
        };

        // Simulate successful chaincode transaction
        const mockTransactionId = `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

        console.log(' [DEMO] Fabric transaction simulated successfully');
        console.log(' [DEMO] IoT Data stored:', JSON.stringify(iotData, null, 2));
        console.log(' [DEMO] Transaction ID:', mockTransactionId);

        await gateway.disconnect();

        res.status(200).send({
            success: true,
            transactionId: mockTransactionId,
            fabricAssetId: `asset_${deviceId}_${Date.now()}`,
            message: 'Data successfully stored in Hyperledger Fabric (Demo Mode)'
        });

    } catch (error) {
        console.error(`Failed to submit transaction: ${error}`);
        res.status(500).send({ message: `Failed to submit transaction: ${error}` });
    }
});

app.listen(port, () => {
    console.log(`Orchestrator listening at http://localhost:${port}`);
});
