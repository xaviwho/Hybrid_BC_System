const { Wallets } = require('fabric-network');
const fs = require('fs');
const path = require('path');

async function main() {
    try {
        // Create a new file system based wallet for managing identities.
        const walletPath = path.join(process.cwd(), 'wallet');
        const wallet = await Wallets.newFileSystemWallet(walletPath);
        console.log(`Wallet path: ${walletPath}`);

        // Check to see if we've already enrolled the appUser.
        const appUserIdentity = await wallet.get('appUser');
        if (appUserIdentity) {
            console.log('An identity for the user "appUser" already exists in the wallet');
            return;
        }

        // Check if admin exists (we need admin to register appUser)
        const adminIdentity = await wallet.get('admin');
        if (!adminIdentity) {
            console.log('Admin identity not found. Please run setupWallet.js first.');
            return;
        }

        // For cryptogen setup, we can use the same admin credentials for appUser
        // In a real CA setup, this would be a separate user registration process
        console.log('Creating appUser identity using admin credentials (cryptogen setup)');
        
        // Read the admin certificate and private key from cryptogen output
        const credPath = path.join(__dirname, '..', 'blockchain', 'setup', 'hyperledger', 'fabric-samples', 'test-network', 'organizations', 'peerOrganizations', 'org1.example.com', 'users', 'Admin@org1.example.com', 'msp');
        const certificate = fs.readFileSync(path.join(credPath, 'signcerts', 'Admin@org1.example.com-cert.pem')).toString();
        const privateKey = fs.readFileSync(path.join(credPath, 'keystore', fs.readdirSync(path.join(credPath, 'keystore'))[0])).toString();

        // Create the appUser identity (using admin creds for simplicity in cryptogen setup)
        const appUserIdentityData = {
            credentials: {
                certificate: certificate,
                privateKey: privateKey,
            },
            mspId: 'Org1MSP',
            type: 'X.509',
        };

        await wallet.put('appUser', appUserIdentityData);
        console.log('Successfully imported appUser identity into the wallet');

    } catch (error) {
        console.error(`Failed to set up appUser: ${error}`);
        process.exit(1);
    }
}

main();
