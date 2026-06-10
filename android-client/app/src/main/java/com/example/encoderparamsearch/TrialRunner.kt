package com.example.encoderparamsearch

import android.media.MediaCodec
import org.json.JSONObject

class TrialRunner(
    private val backendClient: BackendClient,
    private val capabilityReporter: CapabilityReporter,
    private val parameterProxy: EncoderParameterProxy,
    private val extensionStrategy: NoOpExtensionStrategy = NoOpExtensionStrategy(),
) {
    fun registerCapability(sessionId: String): JSONObject {
        return backendClient.registerCapability(sessionId, capabilityReporter.reportAvcEncoder())
    }

    fun runOneTrial(sessionId: String, source: TrialSource): JSONObject {
        val assignment = backendClient.nextTrial(sessionId)
        return try {
            val capability = capabilityReporter.reportAvcEncoder()
            val mapping = parameterProxy.createAvcFormat(
                assignment.requestedParams,
                source.width,
                source.height,
                source.frameRate,
                capability.codec.profiles.toSet(),
            )
            val extensionResult = extensionStrategy.apply(mapping.format, assignment.requestedParams)
            val artifact = encode(source, extensionResult)
            val metadata = TrialResultMetadata(
                appliedParams = mapping.appliedParams,
                appliedParamsUnknown = mapping.appliedParamsUnknown + extensionResult.unknownParams,
                encoderLog = JSONObject()
                    .put("width", source.width)
                    .put("height", source.height)
                    .put("frame_rate", source.frameRate)
                    .put("duration_sec", source.durationSec),
            )
            backendClient.uploadResult(sessionId, assignment.trialId, metadata, artifact)
        } catch (error: Exception) {
            backendClient.markFailure(
                sessionId,
                assignment.trialId,
                "ENCODING_FAILED",
                error.message ?: error.javaClass.simpleName,
            )
        }
    }

    private fun encode(source: TrialSource, extensionResult: ExtensionResult): ByteArray {
        val codec = MediaCodec.createEncoderByType("video/avc")
        return try {
            codec.configure(extensionResult.format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            source.encoder.encode(codec)
        } finally {
            codec.release()
        }
    }
}

data class TrialSource(
    val width: Int,
    val height: Int,
    val frameRate: Int,
    val durationSec: Int,
    val encoder: SourceEncoder,
)

interface SourceEncoder {
    fun encode(codec: MediaCodec): ByteArray
}
