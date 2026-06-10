package com.example.encoderparamsearch

import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

class BackendClient(private val baseUrl: String) {
    fun createSession(
        inputVideoId: String = "android_smoke_test",
        targetMime: String = "video/avc",
        targetCodec: String = "auto",
    ): JSONObject {
        val payload = JSONObject()
            .put("input_video_id", inputVideoId)
            .put("target_mime", targetMime)
            .put("target_codec", targetCodec)
        return postJson("/sessions", payload)
    }

    fun registerCapability(sessionId: String, capability: CapabilityPayload): JSONObject {
        return postJson("/sessions/$sessionId/capabilities", capability.toJson())
    }

    fun nextTrial(sessionId: String): TrialAssignment {
        val response = request("GET", "/sessions/$sessionId/trials/next", null, "application/json")
        val params = response.getJSONObject("requested_params")
        return TrialAssignment(response.getString("trial_id"), params)
    }

    fun uploadResult(
        sessionId: String,
        trialId: String,
        metadata: TrialResultMetadata,
        artifact: ByteArray,
    ): JSONObject {
        val boundary = "encoder-param-search-${System.currentTimeMillis()}"
        val body = ByteArrayOutputStream()
        body.write("--$boundary\r\n".toByteArray())
        body.write("Content-Disposition: form-data; name=\"metadata\"\r\n".toByteArray())
        body.write("Content-Type: application/json\r\n\r\n".toByteArray())
        body.write(metadata.toJson().toString().toByteArray())
        body.write("\r\n--$boundary\r\n".toByteArray())
        body.write("Content-Disposition: form-data; name=\"artifact\"; filename=\"output.h264\"\r\n".toByteArray())
        body.write("Content-Type: application/octet-stream\r\n\r\n".toByteArray())
        body.write(artifact)
        body.write("\r\n--$boundary--\r\n".toByteArray())

        return request(
            "POST",
            "/sessions/$sessionId/trials/$trialId/result",
            body.toByteArray(),
            "multipart/form-data; boundary=$boundary",
        )
    }

    fun markFailure(sessionId: String, trialId: String, code: String, message: String): JSONObject {
        val payload = JSONObject()
            .put("error_code", code)
            .put("error_message", message)
        return postJson("/sessions/$sessionId/trials/$trialId/failure", payload)
    }

    private fun postJson(path: String, payload: JSONObject): JSONObject {
        return request("POST", path, payload.toString().toByteArray(), "application/json")
    }

    private fun request(
        method: String,
        path: String,
        body: ByteArray?,
        contentType: String,
    ): JSONObject {
        val connection = URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.setRequestProperty("Accept", "application/json")
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", contentType)
            connection.outputStream.use { it.write(body) }
        }

        val responseCode = connection.responseCode
        val stream = if (responseCode in 200..299) connection.inputStream else connection.errorStream
        val responseBody = stream.bufferedReader().use { it.readText() }
        if (responseCode !in 200..299) {
            throw BackendException(responseCode, responseBody)
        }
        return JSONObject(responseBody)
    }
}

class BackendException(val statusCode: Int, message: String) : RuntimeException(message)

data class TrialAssignment(
    val trialId: String,
    val requestedParams: JSONObject,
)

data class TrialResultMetadata(
    val appliedParams: JSONObject,
    val appliedParamsUnknown: List<String>,
    val encoderLog: JSONObject,
) {
    fun toJson(): JSONObject {
        return JSONObject()
            .put("applied_params", appliedParams)
            .put("applied_params_unknown", JSONArray(appliedParamsUnknown))
            .put("encoder_log", encoderLog)
    }
}
