const { Wallets } = require('fabric-network');
const FabricCAServices = require('fabric-ca-client');
const fs = require('fs');
const path = require('path');

async function main() {
    try {
        // Create a new file system based wallet for managing identities.
        const walletPath = path.join(process.cwd(), 'wallet');
        const wallet = await Wallets.newFileSystemWallet(walletPath);
        console.log(`Wallet path: ${walletPath}`);

        // Check to see if we've already enrolled the admin user.
        const adminIdentity = await wallet.get('admin');
        if (adminIdentity) {
            console.log('An identity for the admin user "admin" already exists in the wallet');
            return;
        }

        // Read the admin certificate and private key from cryptogen output
        const credPath = path.join(__dirname, '..', 'blockchain', 'setup', 'hyperledger', 'fabric-samples', 'test-network', 'organizations', 'peerOrganizations', 'org1.example.com', 'users', 'Admin@org1.example.com', 'msp');
        const certificate = fs.readFileSync(path.join(credPath, 'signcerts', 'Admin@org1.example.com-cert.pem')).toString();
        const privateKey = fs.readFileSync(path.join(credPath, 'keystore', fs.readdirSync(path.join(credPath, 'keystore'))[0])).toString();

        // Create the admin identity
        const adminIdentityData = {
            credentials: {
                certificate: certificate,
                privateKey: privateKey,
            },
            mspId: 'Org1MSP',
            type: 'X.509',
        };

        await wallet.put('admin', adminIdentityData);
        console.log('Successfully imported admin user "admin" into the wallet');

    } catch (error) {
        console.error(`Failed to set up wallet: ${error}`);
        process.exit(1);
    }
}

main();
