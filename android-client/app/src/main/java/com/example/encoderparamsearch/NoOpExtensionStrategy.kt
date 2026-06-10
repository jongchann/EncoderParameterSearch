package com.example.encoderparamsearch

import android.media.MediaFormat
import org.json.JSONObject

class NoOpExtensionStrategy {
    fun apply(format: MediaFormat, requestedParams: JSONObject): ExtensionResult {
        return ExtensionResult(format, emptyList())
    }
}

data class ExtensionResult(
    val format: MediaFormat,
    val unknownParams: List<String>,
)
