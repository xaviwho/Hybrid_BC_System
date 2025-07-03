// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title AccessToken
 * @dev An ERC721 token that represents a verifiable, on-chain proof of access
 * rights to a specific piece of IoT data. Minting is restricted to a designated minter contract.
 */
contract AccessToken is ERC721, ERC721URIStorage, Ownable {
    uint256 private _tokenIdCounter;
    address public minter;

    /**
     * @dev Throws if called by any account other than the minter.
     */
    modifier onlyMinter() {
        require(minter == msg.sender, "Caller is not the minter");
        _;
    }

    /**
     * @dev Sets the name and symbol for the token collection.
     */
    constructor() ERC721("AccessToken", "ATK") {}

    /**
     * @dev Allows the owner to set the address of the contract permitted to mint tokens.
     * @param _minter The address of the minter contract.
     */
    function setMinter(address _minter) public onlyOwner {
        minter = _minter;
    }

    /**
     * @dev Mints a new access token for a user. Can only be called by the designated minter.
     * The token URI should contain metadata linking to the approved data access request.
     * @param _to The address that will receive the minted token.
     * @param _tokenURI The URI for the token's metadata.
     * @return The ID of the newly minted token.
     */
    function mintAccessToken(address _to, string memory _tokenURI) public onlyMinter returns (uint256) {
        uint256 newTokenId = _tokenIdCounter;
        _safeMint(_to, newTokenId);
        _setTokenURI(newTokenId, _tokenURI);

        _tokenIdCounter++;
        return newTokenId;
    }

    // The following functions are overrides required by Solidity.

    function _burn(uint256 tokenId) internal override(ERC721, ERC721URIStorage) {
        super._burn(tokenId);
    }

    function tokenURI(uint256 tokenId)
        public
        view
        override(ERC721, ERC721URIStorage)
        returns (string memory)
    {
        return super.tokenURI(tokenId);
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721, ERC721URIStorage)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
}
