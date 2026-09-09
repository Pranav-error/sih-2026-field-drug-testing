"""A local bridge so the web demo runs the REAL pipeline.

On a handset, L1 runs natively over a platform channel — OpenCV compiled into the
app. There is no OpenCV in a browser, so a web build has nothing to detect
fiducials with, and the demo was reduced to a button that pretended.

This server closes that gap honestly: the browser posts a frame, `ftr.pipeline`
runs *the same code the tests and the verifier use*, and the real numbers come
back. Nothing is simulated. It is a transport substitute for the platform
channel, not a substitute for the pipeline.

    python core/tools/measure_server.py            # then open the web app

Localhost only, no auth, no persistence. It is a demo rig, not a service.
"""

from __future__ import annotations

import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from ftr.card import CARD_V1                              # noqa: E402
from ftr.colorimetry import ConformalClassifier           # noqa: E402
from ftr.detect import detect_card                        # noqa: E402
from ftr.card import tab_centre_mm                        # noqa: E402
from ftr.parallax import measure_parallax                 # noqa: E402
from ftr.pipeline import measure                          # noqa: E402

# Reference loci for the surrogate ladder the card is printed against. Real
# reagent loci are a data change, not a code change — see ARCHITECTURE.md §7.
LOCI = {
    "opiate_class": np.array([18.4, 23.2, -7.5]),
    "opiate_related": np.array([22.1, 20.4, -4.8]),
    "amphetamine_class": np.array([40.3, 14.3, 26.4]),
    "negative": np.array([80.1, -1.2, 5.9]),
}


def build_classifier(alpha: float = 0.05) -> ConformalClassifier:
    rng = np.random.default_rng(2026)
    labs, labels = [], []
    for name, locus in LOCI.items():
        labs += [locus + rng.normal(0, 2.4, 3) for _ in range(200)]
        labels += [name] * 200
    clf = ConformalClassifier(LOCI, alpha=alpha)
    clf.calibrate(np.array(labs), labels)
    return clf


CLASSIFIER = build_classifier()


def describe(m) -> dict:
    """Everything the capture screen needs, in the units it renders."""
    q = m.quality
    out = {
        "detected": bool(m.detected),
        "fiducials": q.markers_found if q else (
            len(m.detection.markers_found) if m.detection else 0),
        "guidance": m.guidance(),
        "refusals": list(m.refusals),
        "usable": bool(m.usable),
    }
    if q is not None:
        # The gate's own thresholds, mapped to 0..1 so the UI can show progress
        # without inventing its own limits.
        out.update({
            "illumination": max(0.0, 1.0 - q.illumination_residual_stops /
                                max(q.MAX_ILLUM_RESIDUAL, 1e-6)),
            "focus": min(1.0, q.blur / max(q.MIN_BLUR, 1e-9)),
            "tilt_degrees": q.tilt_degrees,
            "clipped": q.clipped_fraction,
            "light_field": q.light_field_residual_stops,
            "gate_passed": bool(q.passed),
        })
    if m.lab is not None:
        out["lab"] = [round(float(v), 1) for v in m.lab]
        out["card_residual"] = round(float(m.transform_residual_delta_e), 3)
    if m.prediction is not None:
        p = m.prediction
        out["prediction"] = {
            "set": list(p.prediction_set),
            "label": p.label,
            "alpha": p.alpha,
            "threshold": round(p.threshold, 2),
            "scores": {k: round(v, 2) for k, v in sorted(p.scores.items())},
            "reason": p.reason,
        }
    return out


def liveness(frame_a: np.ndarray, frame_b: np.ndarray) -> dict:
    """Real two-view parallax on two real frames.

    This is the weaker of the two forms of the check, and says so. The full
    version in `ftr.parallax.check_liveness` compares the measured displacement
    against the displacement a *known* baseline and distance predict, which
    pins the feature's height. A webcam reports neither, so here we test the two
    things that are recoverable without them:

      * the card plane re-aligned between the frames, and
      * the tab region moved against it by more than the noise floor.

    A flat reproduction gives zero on the second for the same geometric reason it
    always does. What this cannot do is reject a reproduction with *some* depth,
    which the full check would.
    """
    det_a, det_b = detect_card(frame_a, CARD_V1), detect_card(frame_b, CARD_V1)
    if det_a is None or det_b is None or not (det_a.complete and det_b.complete):
        return {"checked": False,
                "note": "the card was not found in both frames"}

    r = measure_parallax(frame_a, frame_b, det_a, det_b,
                         tab_centre_mm(CARD_V1), spec=CARD_V1)

    FLOOR_PX = 2.0          # below this is noise, not depth
    PLANE_LIMIT_PX = 3.0    # above this the card itself moved or bent

    if r.confidence < 0.35:
        live, why = False, ("the two frames could not be matched — move less "
                            "between them, or hold steadier")
    elif r.plane_residual_px > PLANE_LIMIT_PX:
        live, why = False, (f"the card did not re-align between frames "
                            f"({r.plane_residual_px:.1f} px): it moved or bent")
    elif r.displacement_px < FLOOR_PX:
        live, why = False, (f"FLAT. {r.displacement_px:.1f} px of parallax at the "
                            "tab. A print or a screen gives zero at any print "
                            "quality, because it is flat")
    else:
        live, why = True, (f"{r.displacement_px:.1f} px of parallax at the tab "
                           "while the card plane re-aligned: the scene has depth")

    return {
        "checked": True,
        "live": live,
        "displacement_px": round(r.displacement_px, 2),
        "plane_residual_px": round(r.plane_residual_px, 2),
        "confidence": round(r.confidence, 2),
        "floor_px": FLOOR_PX,
        "reason": why,
        "form": "weak — no known baseline or distance, so height is not pinned",
    }


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "ok": True,
            "card": CARD_V1.card_id_prefix,
            "classes": sorted(LOCI),
            "note": "the real ftr.pipeline, running behind a localhost bridge",
        }).encode())

    @staticmethod
    def _decode(b64: str) -> np.ndarray:
        img = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8),
                           cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("frame did not decode as an image")
        if img.shape[1] > 1600:
            scale = 1600 / img.shape[1]
            img = cv2.resize(img, None, fx=scale, fy=scale,
                             interpolation=cv2.INTER_AREA)
        return img

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)

            # Two frames: the liveness check, on real images.
            if payload.get("frame_b"):
                a = self._decode(payload["frame"])
                b = self._decode(payload["frame_b"])
                result = describe(measure(a, CLASSIFIER, CARD_V1))
                result["liveness"] = liveness(a, b)
                body = json.dumps(result).encode()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            img = self._decode(payload["frame"])
            result = describe(measure(img, CLASSIFIER, CARD_V1))
        except Exception as e:                                   # noqa: BLE001
            result = {"detected": False, "fiducials": 0,
                      "guidance": "Frame could not be read.", "error": str(e)}

        body = json.dumps(result).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main() -> int:
    port = 8824
    print(f"measure bridge on http://127.0.0.1:{port}")
    print(f"  card    {CARD_V1.card_id_prefix}, {CARD_V1.n_patches} patches, "
          f"{len(CARD_V1.marker_ids)} fiducials")
    print(f"  classes {', '.join(sorted(LOCI))}")
    print(f"  alpha   {CLASSIFIER.alpha}  threshold {CLASSIFIER.threshold:.2f} dE")
    print("  running the same ftr.pipeline the tests and the verifier use")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
