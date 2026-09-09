/// The live viewfinder.
///
/// Shows the real camera where one is available, and says so plainly where it is
/// not. The guidance overlay and the framing rectangle sit on top of the feed
/// because they are instructions to the operator, not decoration.
///
/// **What is real here and what is not.** The camera feed is real. The quality
/// numbers beside it are not yet: fiducial detection, homography and the
/// illumination fit are OpenCV work that runs over a platform channel on a
/// handset, and none of it exists in this build. The panel says so rather than
/// letting a live picture imply a live measurement — a viewfinder that looks like
/// it is measuring when it is not is exactly the kind of thing this project
/// refuses to ship.
library;

import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'tokens.dart';

class Viewfinder extends StatefulWidget {
  const Viewfinder({
    super.key,
    required this.guidance,
    required this.locked,
    this.onFrame,
    this.framePeriod = const Duration(milliseconds: 900),
  });

  final String guidance;
  final bool locked;

  /// Called with a JPEG of the current view, roughly every [framePeriod].
  ///
  /// The viewfinder owns the camera, so it owns the frame loop; the parent only
  /// has to say what to do with a frame. Ticks are skipped while a previous
  /// callback is still running, so a slow measurement cannot queue up behind
  /// the camera.
  final Future<void> Function(Uint8List)? onFrame;
  final Duration framePeriod;

  @override
  State<Viewfinder> createState() => _ViewfinderState();
}

class _ViewfinderState extends State<Viewfinder> {
  CameraController? _controller;
  String? _problem;
  bool _starting = true;
  Timer? _loop;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        _fail('No camera found on this device.');
        return;
      }
      // Rear camera on a handset; on a laptop there is only one.
      final chosen = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        chosen,
        ResolutionPreset.high,
        enableAudio: false,
      );
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() {
        _controller = controller;
        _starting = false;
      });
      if (widget.onFrame != null) {
        _loop = Timer.periodic(widget.framePeriod, (_) => _grab());
      }
    } catch (e) {
      _fail(kIsWeb
          ? 'The browser blocked the camera. Allow camera access and reload — '
              'on a served page this needs https or localhost.'
          : 'Camera unavailable: $e');
    }
  }

  void _fail(String message) {
    if (!mounted) return;
    setState(() {
      _problem = message;
      _starting = false;
    });
  }

  Future<void> _grab() async {
    final c = _controller;
    final onFrame = widget.onFrame;
    if (_busy || c == null || !c.value.isInitialized || onFrame == null) return;
    _busy = true;
    try {
      final shot = await c.takePicture();
      await onFrame(await shot.readAsBytes());
    } catch (_) {
      // A dropped frame is not an error worth surfacing; the next tick retries.
    } finally {
      _busy = false;
    }
  }

  @override
  void dispose() {
    _loop?.cancel();
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 3 / 4,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: Stack(
          fit: StackFit.expand,
          children: [
            _feed(),
            _framingGuide(),
            Positioned(left: 10, right: 10, bottom: 10, child: _hint()),
          ],
        ),
      ),
    );
  }

  Widget _feed() {
    final c = _controller;
    if (c != null && c.value.isInitialized) {
      // Cover the frame rather than letterbox it: the operator is composing a
      // shot, and black bars make it harder to judge how much card is in view.
      return FittedBox(
        fit: BoxFit.cover,
        child: SizedBox(
          width: c.value.previewSize?.height ?? 720,
          height: c.value.previewSize?.width ?? 960,
          child: CameraPreview(c),
        ),
      );
    }
    return ColoredBox(
      color: const Color(0xFF16131F),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 26),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(_starting ? Icons.photo_camera_outlined : Icons.videocam_off_outlined,
                  color: Colors.white24, size: 34),
              const SizedBox(height: 10),
              Text(
                _starting ? 'Starting the camera…' : _problem!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFFB9B3C6), fontSize: 12, height: 1.45),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Where the card should sit. Not a decoration: the card and the reaction well
  /// must be in one frame, on one plane, under one light.
  Widget _framingGuide() {
    return IgnorePointer(
      child: Center(
        child: FractionallySizedBox(
          widthFactor: 0.86,
          heightFactor: 0.62,
          child: DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(
                color: widget.locked
                    ? Tokens.negative
                    : Colors.white.withValues(alpha: 0.55),
                width: 2,
              ),
              borderRadius: BorderRadius.circular(4),
            ),
          ),
        ),
      ),
    );
  }

  Widget _hint() {
    return Container(
      padding: const EdgeInsets.all(9),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.82),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(widget.guidance,
          style: const TextStyle(color: Color(0xFFEDEAF4), fontSize: 12.5)),
    );
  }
}
