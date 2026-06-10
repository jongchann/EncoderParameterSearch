package com.example.encoderparamsearch

import android.graphics.Color
import android.graphics.Paint
import android.media.MediaCodec
import android.os.SystemClock
import java.io.ByteArrayOutputStream

class SyntheticSurfaceSourceEncoder(
    private val width: Int,
    private val height: Int,
    private val frameRate: Int,
    private val durationSec: Int,
) : SourceEncoder {
    override fun encode(codec: MediaCodec): ByteArray {
        val output = ByteArrayOutputStream()
        val bufferInfo = MediaCodec.BufferInfo()
        val inputSurface = codec.createInputSurface()
        codec.start()

        try {
            val frameCount = frameRate * durationSec
            var nextFrame = 0
            var inputFinished = false
            var outputFinished = false

            while (!outputFinished) {
                if (!inputFinished && nextFrame < frameCount) {
                    drawFrame(inputSurface, nextFrame)
                    nextFrame += 1
                    if (nextFrame == frameCount) {
                        codec.signalEndOfInputStream()
                        inputFinished = true
                    }
                }

                when (val outputBufferId = codec.dequeueOutputBuffer(bufferInfo, DEQUEUE_TIMEOUT_US)) {
                    MediaCodec.INFO_TRY_AGAIN_LATER -> Unit
                    MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> writeCodecConfig(codec, output)
                    else -> {
                        if (outputBufferId >= 0) {
                            val outputBuffer = codec.getOutputBuffer(outputBufferId)
                            if (outputBuffer != null && bufferInfo.size > 0) {
                                val encoded = ByteArray(bufferInfo.size)
                                outputBuffer.position(bufferInfo.offset)
                                outputBuffer.limit(bufferInfo.offset + bufferInfo.size)
                                outputBuffer.get(encoded)
                                output.write(encoded)
                            }
                            outputFinished = bufferInfo.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                            codec.releaseOutputBuffer(outputBufferId, false)
                        }
                    }
                }

                if (!inputFinished) {
                    SystemClock.sleep(FRAME_PACING_MS)
                }
            }
        } finally {
            inputSurface.release()
            codec.stop()
        }

        return output.toByteArray()
    }

    private fun drawFrame(surface: android.view.Surface, frameIndex: Int) {
        val canvas = surface.lockCanvas(null)
        try {
            val paint = Paint(Paint.ANTI_ALIAS_FLAG)
            val hue = (frameIndex * 11) % 255
            canvas.drawColor(Color.rgb(hue, 255 - hue, 96))
            paint.color = Color.WHITE
            paint.textSize = height / 12f
            canvas.drawText("EncoderParamSearch", width * 0.08f, height * 0.45f, paint)
            canvas.drawText("frame $frameIndex", width * 0.08f, height * 0.58f, paint)
        } finally {
            surface.unlockCanvasAndPost(canvas)
        }
    }

    private fun writeCodecConfig(codec: MediaCodec, output: ByteArrayOutputStream) {
        val format = codec.outputFormat
        for (key in listOf("csd-0", "csd-1")) {
            val buffer = format.getByteBuffer(key) ?: continue
            val bytes = ByteArray(buffer.remaining())
            buffer.get(bytes)
            output.write(bytes)
        }
    }

    companion object {
        private const val DEQUEUE_TIMEOUT_US = 10_000L
        private const val FRAME_PACING_MS = 1L
    }
}
