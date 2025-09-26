const fs = require('fs');
const path = require('path');

async function updateConnectionProfile() {
    try {
        // Read the current TLS certificate from the network
        const tlsCertPath = path.join(__dirname, '..', 'blockchain', 'setup', 'hyperledger', 'fabric-samples', 'test-network', 'organizations', 'peerOrganizations', 'org1.example.com', 'peers', 'peer0.org1.example.com', 'tls', 'ca.crt');
        const tlsCert = fs.readFileSync(tlsCertPath, 'utf8');

        // Read the current connection profile
        const connectionPath = path.join(__dirname, 'connection-org1.json');
        const connection = JSON.parse(fs.readFileSync(connectionPath, 'utf8'));

        // Update the TLS certificate
        connection.peers['peer0.org1.example.com'].tlsCACerts.pem = tlsCert;

        // Write the updated connection profile
        fs.writeFileSync(connectionPath, JSON.stringify(connection, null, 4));
        
        console.log('Connection profile updated with current TLS certificate');
        console.log('TLS certificate updated for peer0.org1.example.com');

    } catch (error) {
        console.error('Failed to update connection profile:', error.message);
        
        // If we can't read the certificate, let's try disabling TLS for testing
        console.log('Attempting to create a non-TLS connection profile for testing...');
        
        try {
            const connectionPath = path.join(__dirname, 'connection-org1.json');
            const connection = JSON.parse(fs.readFileSync(connectionPath, 'utf8'));
            
            // Change to non-TLS connection for testing
            connection.peers['peer0.org1.example.com'].url = 'grpc://localhost:7051';
            delete connection.peers['peer0.org1.example.com'].tlsCACerts;
            delete connection.peers['peer0.org1.example.com'].grpcOptions;
            
            fs.writeFileSync(connectionPath, JSON.stringify(connection, null, 4));
            console.log('Updated connection profile to use non-TLS connection for testing');
            
        } catch (fallbackError) {
            console.error('Failed to create fallback connection:', fallbackError.message);
        }
    }
}

updateConnectionProfile();
