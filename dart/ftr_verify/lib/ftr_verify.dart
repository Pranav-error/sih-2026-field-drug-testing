/// Field Test Records — the second implementation.
///
/// Public surface of the package. Everything the app and the CLI need is exported
/// here; `lib/src/` is private and may be rearranged without breaking either.
///
///   canonical CBOR   deterministic encoding — the digest is the legal artefact
///   record           envelope parsing, digest recomputation, signature check
///   seal             building and sealing a record on the device
///   verifier         proven / asserted / unverifiable
///   colorimetry      L1 device transform and L2 conformal abstention
///
/// See README.md for what "independent implementation" means here, and
/// ../../docs/DETERMINISM.md for what agreement between the two actually buys.
library;

export 'src/canonical_cbor.dart' show encode, decode, isCanonical, CborError;
export 'src/colorimetry.dart';
export 'src/record.dart' show SealedRecord, sha256, hex, bytesEqual, genesisHash;
export 'src/seal.dart'
    show Attestation, Keystore, SoftwareKeystore, buildBody, seal, toEnvelope, schemaVersion;
export 'src/verifier.dart' show Report, verifyRecord, verifyChain;
