# Electrum - Lightweight Bitcoin Client
# Copyright (c) 2012 Thomas Voegtlin
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from .bitcoin import hash_decode, hash_encode
from .crypto import sha256d
from .logs import logs
from .networks import Net
from .transaction import Transaction
from .util import ThreadJob, bh2u


logger = logs.get_logger("verifier")


class InnerNodeOfSpvProofIsValidTx(Exception): pass

class SPV(ThreadJob):
    """ Simple Payment Verification """

    def __init__(self, network, wallet):
        self.wallet = wallet
        self.network = network
        self.blockchain = network.blockchain()
        self.merkle_roots = {}  # txid -> merkle root (once it has been verified)
        self.requested_merkle = set()  # txid set of pending requests

    def run(self):
        interface = self.network.interface
        if not interface:
            logger.error("no interface")
            return

        blockchain = interface.blockchain
        if not blockchain:
            logger.error("no blockchain for interface '%s'", interface.server)
            return

        local_height = self.network.get_local_height()
        unverified = self.wallet.get_unverified_txs()
        for tx_hash, tx_height in unverified.items():
            # do not request merkle branch if we already requested it
            if tx_hash in self.requested_merkle or tx_hash in self.merkle_roots:
                continue
            # or before headers are available
            if tx_height <= 0 or tx_height > local_height:
                continue

            # if it's in the checkpoint region, we still might not have the header
            header = blockchain.read_header(tx_height)
            if header is None:
                if tx_height <= Net.VERIFICATION_BLOCK_HEIGHT:
                    # Per-header requests might be a lot heavier.
                    # Also, they're not supported as header requests are
                    # currently designed for catching up post-checkpoint headers.
                    index = tx_height // 2016
                    if self.network.request_chunk(interface, index):
                        interface.logger.debug("verifier requesting chunk %s for height %s",
                                               index, tx_height)
                continue
            # request now
            self.network.get_merkle_for_transaction(
                    tx_hash,
                    tx_height,
                    self.verify_merkle)
            logger.debug('requested merkle %s', tx_hash)
            self.requested_merkle.add(tx_hash)

        if self.network.blockchain() != self.blockchain:
            self.blockchain = self.network.blockchain()
            self.undo_verifications()

    def verify_merkle(self, response):
        if self.wallet.verifier is None:
            return  # we have been killed, this was just an orphan callback
        if response.get('error'):
            logger.error('received an error %s', response)
            return
        params = response['params']
        merkle = response['result']
        # Verify the hash of the server-provided merkle branch to a
        # transaction matches the merkle root of its block
        tx_hash = params[0]
        tx_height = merkle.get('block_height')
        pos = merkle.get('pos')
        try:
            merkle_root = self.hash_merkle_root(merkle['merkle'], tx_hash, pos)
        except InnerNodeOfSpvProofIsValidTx:
            logger.error("merkle verification failed for %s (inner node looks like tx)",
                             tx_hash)
            return

        header = self.network.blockchain().read_header(tx_height)
        # FIXME: if verification fails below,
        # we should make a fresh connection to a server to
        # recover from this, as this TX will now never verify
        if not header:
            logger.error(
                "merkle verification failed for %s (missing header %s)",
                tx_hash, tx_height)
            return
        if header.get('merkle_root') != merkle_root:
            logger.error(
                "merkle verification failed for %s (merkle root mismatch %s != %s)",
                tx_hash, header.get('merkle_root'), merkle_root)
            return
        # we passed all the tests
        self.merkle_roots[tx_hash] = merkle_root
        try:
            # note: we could pop in the beginning, but then we would request
            # this proof again in case of verification failure from the same server
            self.requested_merkle.remove(tx_hash)
        except KeyError:
            pass
        logger.debug("verified %s", tx_hash)
        self.wallet.add_verified_tx(tx_hash, (tx_height, header.get('timestamp'), pos))
        if self.is_up_to_date() and self.wallet.is_up_to_date():
            self.wallet.save_verified_tx(write=True)

    @classmethod
    def hash_merkle_root(cls, merkle_s, target_hash, pos):
        h = hash_decode(target_hash)
        for i, item in enumerate(merkle_s):
            if (pos >> i) & 1:
                h = sha256d(hash_decode(item) + h)
            else:
                h = sha256d(h + hash_decode(item))
            cls._raise_if_valid_tx(bh2u(h))
        return hash_encode(h)

    @classmethod
    def _raise_if_valid_tx(cls, raw_tx: str):
        # If an inner node of the merkle proof is also a valid tx, chances are, this is an attack.
        # https://lists.linuxfoundation.org/pipermail/bitcoin-dev/2018-June/016105.html
        # https://goo.gl/qJnSbQ
        # https://bitcoin.stackexchange.com/questions/76121
        tx = Transaction(raw_tx)
        try:
            tx.deserialize()
        except:
            pass
        else:
            raise InnerNodeOfSpvProofIsValidTx()

    def undo_verifications(self):
        height = self.blockchain.get_base_height()
        tx_hashes = self.wallet.undo_verifications(self.blockchain, height)
        for tx_hash in tx_hashes:
            logger.debug("redoing %s", tx_hash)
            self.remove_spv_proof_for_tx(tx_hash)

    def remove_spv_proof_for_tx(self, tx_hash):
        self.merkle_roots.pop(tx_hash, None)
        try:
            self.requested_merkle.remove(tx_hash)
        except KeyError:
            pass

    def is_up_to_date(self):
        return not self.requested_merkle
