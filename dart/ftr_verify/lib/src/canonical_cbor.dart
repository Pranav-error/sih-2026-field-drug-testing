/// Canonical CBOR — deterministic encoding, RFC 8949 §4.2.1 core rules.
///
/// This is a **second, independent implementation** of the profile in
/// `core/ftr/canonical_cbor.py`. That is the entire point of it. The digest of a
/// Field Test Record is what a §63 certificate must state, and a digest is only
/// worth stating if two people who wrote two encoders separately arrive at the
/// same bytes. A single implementation agreeing with itself proves nothing.
///
/// The profile, restated here so this file can be read without the Python:
///
///   * definite lengths only — no streaming forms
///   * shortest-form integer and length encoding
///   * map keys sorted bytewise-lexicographically by their *encoded* bytes
///   * no floats, no tags, no duplicate keys
///
/// Floats are refused rather than canonicalised: every measured quantity in a
/// record is a scaled integer with its scale named in the field.
library;

import 'dart:convert';
import 'dart:typed_data';

class CborError implements Exception {
  final String message;
  CborError(this.message);
  @override
  String toString() => 'CborError: $message';
}

// --------------------------------------------------------------------------- //
// encoding
// --------------------------------------------------------------------------- //

void _writeHead(BytesBuilder out, int major, int n) {
  if (n < 0) throw CborError('negative argument $n');
  final m = major << 5;
  if (n < 24) {
    out.addByte(m | n);
  } else if (n < 0x100) {
    out..addByte(m | 24)..addByte(n);
  } else if (n < 0x10000) {
    out.addByte(m | 25);
    out.add([(n >> 8) & 0xff, n & 0xff]);
  } else if (n < 0x100000000) {
    out.addByte(m | 26);
    out.add([(n >> 24) & 0xff, (n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff]);
  } else {
    // Dart ints are 64-bit signed. Values at or above 2^63 cannot be represented,
    // and nothing in a record needs them; refusing beats silently wrapping.
    if (n < 0) throw CborError('integer out of range');
    out.addByte(m | 27);
    for (var s = 56; s >= 0; s -= 8) {
      out.addByte((n >> s) & 0xff);
    }
  }
}

void _encodeInto(BytesBuilder out, Object? v) {
  if (v == null) {
    out.addByte(0xf6);
  } else if (v is bool) {
    out.addByte(v ? 0xf5 : 0xf4);
  } else if (v is int) {
    if (v >= 0) {
      _writeHead(out, 0, v);
    } else {
      _writeHead(out, 1, -v - 1);
    }
  } else if (v is double) {
    throw CborError('floats are not encodable in an FTR — store a scaled integer '
        'and name the scale in the field (e.g. delta_e_x1000)');
  } else if (v is Uint8List) {
    // Only Uint8List is a byte string. A plain List<int> encodes as an array of
    // integers, which mirrors Python's bytes-versus-list distinction exactly — the
    // two implementations must not disagree about what a value *is*.
    _writeHead(out, 2, v.length);
    out.add(v);
  } else if (v is String) {
    final b = utf8.encode(v);
    _writeHead(out, 3, b.length);
    out.add(b);
  } else if (v is List) {
    _writeHead(out, 4, v.length);
    for (final x in v) {
      _encodeInto(out, x);
    }
  } else if (v is Map) {
    final items = <MapEntry<Uint8List, Uint8List>>[];
    v.forEach((k, val) {
      if (k is! String && k is! int) {
        throw CborError('map keys must be String or int, got ${k.runtimeType}');
      }
      items.add(MapEntry(encode(k), encode(val)));
    });
    items.sort((a, b) => _compareBytes(a.key, b.key));
    for (var i = 1; i < items.length; i++) {
      if (_compareBytes(items[i - 1].key, items[i].key) == 0) {
        throw CborError('duplicate map key after encoding');
      }
    }
    _writeHead(out, 5, items.length);
    for (final e in items) {
      out..add(e.key)..add(e.value);
    }
  } else {
    throw CborError('type not encodable in an FTR: ${v.runtimeType}');
  }
}

int _compareBytes(Uint8List a, Uint8List b) {
  final n = a.length < b.length ? a.length : b.length;
  for (var i = 0; i < n; i++) {
    if (a[i] != b[i]) return a[i] - b[i];
  }
  return a.length - b.length;
}

/// Encode [value] canonically.
Uint8List encode(Object? value) {
  final out = BytesBuilder(copy: false);
  _encodeInto(out, value);
  return out.toBytes();
}

// --------------------------------------------------------------------------- //
// decoding
// --------------------------------------------------------------------------- //

class _Reader {
  final Uint8List buf;
  int i = 0;
  _Reader(this.buf);

  (int, int) readHead() {
    if (i >= buf.length) throw CborError('truncated: expected a type byte');
    final ib = buf[i++];
    final major = ib >> 5;
    final minor = ib & 0x1f;
    if (minor < 24) return (major, minor);
    if (minor == 31) throw CborError('indefinite-length item is not canonical');
    if (minor > 27) throw CborError('reserved additional-information value $minor');
    final width = 1 << (minor - 24);
    if (i + width > buf.length) {
      throw CborError('truncated: argument runs past end of buffer');
    }
    var n = 0;
    for (var k = 0; k < width; k++) {
      n = (n << 8) | buf[i + k];
    }
    i += width;
    if (n < 0) throw CborError('integer too large for this implementation');
    // Shortest-form check: a longer encoding of a small value is not canonical.
    const limits = {1: 24, 2: 0x100, 4: 0x10000, 8: 0x100000000};
    if (n < limits[width]!) {
      throw CborError('non-canonical: $n encoded in $width byte(s), shorter form exists');
    }
    return (major, n);
  }

  Object? read() {
    final (major, n) = readHead();
    switch (major) {
      case 0:
        return n;
      case 1:
        return -1 - n;
      case 2:
        if (i + n > buf.length) throw CborError('truncated byte string');
        final b = Uint8List.sublistView(buf, i, i + n);
        i += n;
        return Uint8List.fromList(b);
      case 3:
        if (i + n > buf.length) throw CborError('truncated text string');
        final b = Uint8List.sublistView(buf, i, i + n);
        i += n;
        try {
          return utf8.decode(b);
        } on FormatException {
          throw CborError('invalid UTF-8 in text string');
        }
      case 4:
        return List<Object?>.generate(n, (_) => read(), growable: false);
      case 5:
        final out = <Object?, Object?>{};
        Uint8List? prev;
        for (var k = 0; k < n; k++) {
          final start = i;
          final key = read();
          final enc = Uint8List.fromList(Uint8List.sublistView(buf, start, i));
          if (prev != null && _compareBytes(enc, prev) <= 0) {
            throw CborError('non-canonical: map keys out of order or duplicated');
          }
          prev = enc;
          out[key] = read();
        }
        return out;
      case 7:
        if (n == 20) return false;
        if (n == 21) return true;
        if (n == 22) return null;
        throw CborError('simple/float value $n is not permitted in an FTR');
      default:
        throw CborError('unsupported major type $major');
    }
  }
}

/// Decode [buf], rejecting anything a canonical encoder could not have produced.
Object? decode(Uint8List buf) {
  final r = _Reader(buf);
  final v = r.read();
  if (r.i != buf.length) {
    throw CborError('${buf.length - r.i} trailing byte(s) after the top-level item');
  }
  return v;
}

/// True if [buf] decodes and re-encodes to itself, byte for byte.
bool isCanonical(Uint8List buf) {
  try {
    return _compareBytes(encode(decode(buf)), buf) == 0;
  } on CborError {
    return false;
  }
}
