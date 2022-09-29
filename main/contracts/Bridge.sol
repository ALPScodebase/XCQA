// SPDX-License-Identifier: MIT
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

import {RLPReader} from "./lib/RLPReader.sol";
import {MerklePatriciaProofVerifier} from "./lib/MerklePatriciaProofVerifier.sol";

/**
 *  @title Bridge smart contract for cross-chain query authentication
 *  @author Matteo Loporchio
 *
 *  @dev The main goal of this contract is to allow users
 *  of a "source" blockchain C1 to read values from another "target" chain C2.
 *  The value is guaranteed to be authentic thanks to appropriate
 *  verification mechanisms based on cryptography.
 */
contract Bridge {
  using RLPReader for RLPReader.RLPItem;
  using RLPReader for bytes;

  // Counts the total number of requests.
  uint private requestCounter;
  // Counts the number of served requests.
  uint private servedCounter;
  // Number of most recent blocks to keep inside the contract.
  uint private cacheSize;
  // TODO: require a fee for protecting from DOS attacks.
  uint private requestFee;

  ///
  // struct Header {
  //   bytes32 stateRootHash;
  //   uint256 number;
  //   uint256 timestamp;
  //   //bytes32 hash;
  // }

  /**
   *  @dev Represents a generic request that is submitted to the contract.
   *  A C1 user wants to read the value of a variable located inside
   *  a given contract on C2.
   */
  struct Request {
    address account; // Address of the C2 contract we want to read data from.
    uint key; // Numeric identifier of the C2 variable we want to read.
    uint blockId; // Identifier of the C2 block we want to read data from.
    uint date; // Timestamp of the request.
    uint liveness; // TODO: add expiration.
    uint reward; // TODO: add rewards.
    bool served;  // Equals true if the request has been served, false otherwise.
    bytes response; // The value associated with the variable.
  }

  /**
   *  @dev Represents a generic Ethereum state proof.
   */
  struct StateProof {
    bytes32 stateRoot; // Root of the block the proof is computed from.
    address account; // Address of the C2 contract
    bytes[] accountProof; // Proof that certifies the existence of the contract
    bytes32 storageHash; // 
    bytes key; //
    bytes value; //
    bytes[] storageProof; // Proof that certifies the existence of the variable inside the contract
  }

  /**
   *  @dev Represents a generic Ethereum account.
   */
  struct Account {
    bool exists;
    uint256 nonce;
    uint256 balance;
    bytes32 storageRoot;
    bytes32 codeHash;
  }

  // Header[] private headers;

  /**
   *  @dev This data structure keeps track of all requests.
   *  NOTICE: the id of a request coincides with its index in the array.
   */
  Request[] private requests;

  /**
   *  @dev This event is emitted whenever a new request is created
   *  and saved inside the contract.
   */
  event RequestLogged(
    uint indexed requestId, // Request identifier
    address account, // Address of C2 contract
    uint key, // Numeric identifier of the variable
    uint blockId // Identifier of C2 block
  );

  /**
   *  @dev This event is emitted whenever a request is correctly answered
   *  (i.e., the corresponding value is verified as authentic).
   */
  event RequestServed(
    uint indexed requestId, // Request identifier
    address account, // Address of C2 contract
    uint key, // Numeric identifier of the variable
    uint blockId, // Identifier of C2 block
    bytes reply // Response received by C2 node
  );

  /**
   *  @dev Returns the total number of received requests.
   *  @return the total number of requests received by the contract
   */
  function getTotal() public view returns (uint) {
    return requestCounter;
  }

  /**
   *  @dev Returns the number of served requests.
   *  @return the total number of requests served by the contract
   */
  function getServed() public view returns (uint) {
    return servedCounter;
  }

  /**
   *  @dev Returns the number of pending (i.e., not served) requests.
   *  @return the total number of pending requests
   */
  function getPending() public view returns (uint) {
    return requestCounter-servedCounter;
  }

  /**
   *  @dev Returns the request with the given identifier.
   *  @param id identifier of the request
   *  @return the request with the specified identifier
   */
  function getRequest(uint id) public view returns (Request memory) {
    // Check if the supplied index is legal.
    require(0 <= id && id < requests.length, "Error: invalid request id.");
    return requests[id];
  }

  /**
   *  @dev Returns the cache size of the contract (i.e., number of stored headers).
   *  @return the cache size for the contract
   */
  function getCacheSize() public view returns (uint) {
    return cacheSize;
  }

  /**
   *  @dev Returns the request fee of all requests sent by the contract
   *  @return the request fee associated with all requests
   */
  function getRequestFee() public view returns (uint) {
    return requestFee;
  }

  /**
   *  @dev Returns the full list of requests stored in the contract.
   *  @return the list of all requests stored in the contract
   */
  function getRequests() public view returns (Request[] memory) {
    return requests;
  }

  /**
   *  @dev Returns the full list of block headers stored in the contract.
   *  @return the list of all requests stored in the contract
   */
  // function getHeaders() public view returns (Header[] memory) {
  //   return headers;
  // }

  /**
   *  @dev Returns the full list of block headers stored in the contract.
   *  @return the list of all requests stored in the contract
   */
  // function addHeader(bytes32 _stateRootHash, uint256 _number, uint256 _timestamp) public {
  //   Header memory result;
  //   result.stateRootHash = _stateRootHash;
  //   result.number = _number;
  //   result.timestamp = _timestamp;
  //   headers.push(result);
  // }

  /**
   *  @dev This function creates a new request and submits it to the contract.
   *
   *  @param _account the contract address
   *  @param _key the variable identifier
   *  @param _blockId the identifier of the block from which we want to read the state
   *  @param _liveness (not used)
   *  @param _reward (not used)
   *
   *  @return the identifier of the newly created request.
   *
   *  TODO: add liveness and request fee (and make the function payable).
   */
  function request(address _account, uint _key, uint _blockId, uint _liveness,
  uint _reward) public returns (uint) {
    Request memory r;
    uint requestId = requestCounter;
    r.account = _account;
    r.key = _key;
    r.blockId = _blockId;
    r.date = block.timestamp;
    r.liveness = _liveness;
    r.reward = _reward;
    r.served = false;
    requests.push(r);
    emit RequestLogged(requestId, _account, _key, _blockId);
    requestCounter++;
    return requestId;
  }

  /**
   *  @dev This method can be used to verify an Ethereum state proof.
   *  The proof certifies that a given variable X inside a contract C
   *  has a certain value V.
   *
   *  Ethereum state proofs are made up of two distinct parts:
   *
   *    1) An account proof, which certifies the existence of C.
   *    2) A storage proof, which certifies the existence of X=V inside C.
   *
   *  @param _requestId identifier of the request to be verified
   *  @param _stateProof proof for the request
   *  @return true if and only if the verification process succeeds
   */
  function verify(uint _requestId, StateProof memory _stateProof) public returns (bool) {
    // Convert account proof to a list of RLPItems.
    RLPReader.RLPItem[] memory accountProof = new RLPReader.RLPItem[](_stateProof.accountProof.length);
    for (uint i = 0; i < _stateProof.accountProof.length; i++) {
      accountProof[i] = RLPReader.toRlpItem(_stateProof.accountProof[i]);
    }
    // Verify the account proof.
    bytes memory acctRlpBytes = MerklePatriciaProofVerifier.extractProofValue(
      _stateProof.stateRoot,
      abi.encodePacked(keccak256(abi.encodePacked(_stateProof.account))),
      accountProof
    );
    // If verification has failed, return immediately.
    if (acctRlpBytes.length == 0) return false;
    // Otherwise, we can use the result to decode the account fields.
    Account memory account;
    RLPReader.RLPItem[] memory acctFields = acctRlpBytes.toRlpItem().toList();
    require(acctFields.length == 4);
    account.exists = true;
    account.nonce = acctFields[0].toUint();
    account.balance = acctFields[1].toUint();
    account.storageRoot = bytes32(acctFields[2].toUint());
    account.codeHash = bytes32(acctFields[3].toUint());
    // At this point, we are ready to verify the storage proof, which
    // constitutes the second part of the state proof.
    bytes32 slotHash = keccak256(abi.encodePacked(_stateProof.key));
    // We convert the storage proof to a list of RLPItems.
    uint storageProofLength = _stateProof.storageProof.length;
    RLPReader.RLPItem[] memory storageProof = new RLPReader.RLPItem[](storageProofLength);
    for (uint i = 0; i < storageProofLength; i++) {
      storageProof[i] = RLPReader.toRlpItem(_stateProof.storageProof[i]);
    }
    // Verify the storage proof.
    bytes memory valueRlpBytes = MerklePatriciaProofVerifier.extractProofValue(
      _stateProof.storageHash,
      abi.encodePacked(slotHash),
      storageProof
    );
    if (valueRlpBytes.length == 0) return false;
    // The proof is accepted: first we record this fact on the blockchain.
    requests[_requestId].served = true;
    requests[_requestId].response = RLPReader.toRlpItem(valueRlpBytes).toBytes();
    // Then we trigger a `RequestServed` event to notify all possible listeners.
    emit RequestServed(
      _requestId, requests[_requestId].account,
      requests[_requestId].key, requests[_requestId].blockId, RLPReader.toRlpItem(valueRlpBytes).toBytes()
    );
    return true;
  }
}
