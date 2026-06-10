package com.example.encoderparamsearch

import android.media.MediaCodecInfo
import android.media.MediaFormat
import org.json.JSONObject

class EncoderParameterProxy {
    fun createAvcFormat(
        requestedParams: JSONObject,
        width: Int,
        height: Int,
        frameRate: Int,
        supportedProfiles: Set<String>,
    ): ParameterMappingResult {
        val format = MediaFormat.createVideoFormat("video/avc", width, height)
        val applied = JSONObject()
        val unknown = mutableListOf<String>()

        if (requestedParams.has("bitrate_kbps")) {
            val bitrateBps = requestedParams.getInt("bitrate_kbps") * 1000
            format.setInteger(MediaFormat.KEY_BIT_RATE, bitrateBps)
            applied.put("bitrate_kbps", requestedParams.getInt("bitrate_kbps"))
        }

        if (requestedParams.has("i_frame_interval_sec")) {
            val intervalSec = requestedParams.getDouble("i_frame_interval_sec").toFloat()
            format.setFloat(MediaFormat.KEY_I_FRAME_INTERVAL, intervalSec)
            applied.put("i_frame_interval_sec", requestedParams.get("i_frame_interval_sec"))
        }

        format.setInteger(MediaFormat.KEY_FRAME_RATE, frameRate)
        format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)

        if (requestedParams.has("profile")) {
            val profile = requestedParams.getString("profile")
            val codecProfile = avcProfileValue(profile)
            if (codecProfile != null && supportedProfiles.contains(profile)) {
                format.setInteger(MediaFormat.KEY_PROFILE, codecProfile)
                applied.put("profile", profile)
            } else {
                unknown.add("profile")
            }
        }

        return ParameterMappingResult(format, applied, unknown)
    }

    private fun avcProfileValue(profile: String): Int? {
        return when (profile) {
            "baseline" -> MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline
            "main" -> MediaCodecInfo.CodecProfileLevel.AVCProfileMain
            "high" -> MediaCodecInfo.CodecProfileLevel.AVCProfileHigh
            else -> null
        }
    }
}

data class ParameterMappingResult(
    val format: MediaFormat,
    val appliedParams: JSONObject,
    val appliedParamsUnknown: List<String>,
)
