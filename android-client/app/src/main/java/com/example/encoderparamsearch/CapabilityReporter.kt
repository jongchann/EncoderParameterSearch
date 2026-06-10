package com.example.encoderparamsearch

import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject

class CapabilityReporter {
    fun reportAvcEncoder(): CapabilityPayload {
        val codecInfo = findEncoder("video/avc")
            ?: throw IllegalStateException("No H.264/AVC encoder found on this device.")
        val capabilities = codecInfo.getCapabilitiesForType("video/avc")
        val encoderCapabilities = capabilities.encoderCapabilities

        return CapabilityPayload(
            device = DevicePayload(
                model = Build.MODEL ?: "android-device",
                androidVersion = Build.VERSION.RELEASE ?: "unknown",
                socVendor = Build.HARDWARE ?: "unknown",
            ),
            codec = CodecPayload(
                codecName = codecInfo.name,
                mimeType = "video/avc",
                profiles = capabilities.profileLevels.mapNotNull { avcProfileName(it.profile) }.distinct(),
                bitrateModes = bitrateModeNames(encoderCapabilities),
                supportsBFrame = false,
                vendorKeys = emptyList(),
            ),
            rawPayload = JSONObject()
                .put("codec_name", codecInfo.name)
                .put("canonical_name", canonicalName(codecInfo))
                .put("is_hardware_accelerated", isHardwareAccelerated(codecInfo)),
        )
    }

    private fun findEncoder(mimeType: String): MediaCodecInfo? {
        return MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos.firstOrNull {
            it.isEncoder && it.supportedTypes.any { supported -> supported.equals(mimeType, ignoreCase = true) }
        }
    }

    private fun avcProfileName(profile: Int): String? {
        return when (profile) {
            MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline -> "baseline"
            MediaCodecInfo.CodecProfileLevel.AVCProfileMain -> "main"
            MediaCodecInfo.CodecProfileLevel.AVCProfileHigh -> "high"
            else -> null
        }
    }

    private fun bitrateModeNames(
        encoderCapabilities: MediaCodecInfo.EncoderCapabilities,
    ): List<String> {
        val modes = mutableListOf<String>()
        if (encoderCapabilities.isBitrateModeSupported(
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR,
            )
        ) {
            modes.add("cbr")
        }
        if (encoderCapabilities.isBitrateModeSupported(
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR,
            )
        ) {
            modes.add("vbr")
        }
        if (encoderCapabilities.isBitrateModeSupported(
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CQ,
            )
        ) {
            modes.add("cq")
        }
        return modes
    }

    private fun canonicalName(codecInfo: MediaCodecInfo): String {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) codecInfo.canonicalName else codecInfo.name
    }

    private fun isHardwareAccelerated(codecInfo: MediaCodecInfo): Boolean? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) codecInfo.isHardwareAccelerated else null
    }
}

data class CapabilityPayload(
    val device: DevicePayload,
    val codec: CodecPayload,
    val rawPayload: JSONObject,
) {
    fun toJson(): JSONObject {
        return JSONObject()
            .put("device", device.toJson())
            .put("codec", codec.toJson())
            .put("raw_payload", rawPayload)
    }
}

data class DevicePayload(
    val model: String,
    val androidVersion: String,
    val socVendor: String,
) {
    fun toJson(): JSONObject {
        return JSONObject()
            .put("model", model)
            .put("android_version", androidVersion)
            .put("soc_vendor", socVendor)
    }
}

data class CodecPayload(
    val codecName: String,
    val mimeType: String,
    val profiles: List<String>,
    val bitrateModes: List<String>,
    val supportsBFrame: Boolean,
    val vendorKeys: List<String>,
) {
    fun toJson(): JSONObject {
        return JSONObject()
            .put("codec_name", codecName)
            .put("mime_type", mimeType)
            .put("profiles", JSONArray(profiles))
            .put("bitrate_modes", JSONArray(bitrateModes))
            .put("supports_b_frame", supportsBFrame)
            .put("vendor_keys", JSONArray(vendorKeys))
    }
}
