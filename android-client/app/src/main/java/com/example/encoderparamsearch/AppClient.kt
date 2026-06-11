package com.example.encoderparamsearch

import org.json.JSONObject

interface AppClient {
    fun createSession(): JSONObject
    fun registerCapability(sessionId: String): JSONObject
    fun runOneTrial(sessionId: String, source: TrialSource): JSONObject
}

class NetworkAppClient(private val backendUrl: String) : AppClient {
    private val backendClient = BackendClient(backendUrl)
    private val trialRunner = TrialRunner(
        backendClient,
        CapabilityReporter(),
        EncoderParameterProxy(),
    )

    override fun createSession(): JSONObject {
        return backendClient.createSession()
    }

    override fun registerCapability(sessionId: String): JSONObject {
        return trialRunner.registerCapability(sessionId)
    }

    override fun runOneTrial(sessionId: String, source: TrialSource): JSONObject {
        return trialRunner.runOneTrial(sessionId, source)
    }
}

class MockAppClient : AppClient {
    override fun createSession(): JSONObject {
        return JSONObject()
            .put("session_id", "mock_sess_001")
            .put("status", "created")
    }

    override fun registerCapability(sessionId: String): JSONObject {
        return JSONObject()
            .put("session_id", sessionId)
            .put("status", "ready")
            .put("device_id", "mock_device")
            .put("capability_id", "mock_capability")
            .put("search_space_version", 1)
    }

    override fun runOneTrial(sessionId: String, source: TrialSource): JSONObject {
        return JSONObject()
            .put("trial_id", "mock_trial_001")
            .put("status", "uploaded")
            .put(
                "requested_params",
                JSONObject()
                    .put("bitrate_kbps", 4000)
                    .put("i_frame_interval_sec", 2)
                    .put("profile", "baseline"),
            )
            .put(
                "applied_params",
                JSONObject()
                    .put("bitrate_kbps", 4000)
                    .put("i_frame_interval_sec", 2)
                    .put("profile", "baseline"),
            )
            .put("artifact_path", "mock://$sessionId/trials/mock_trial_001/output.h264")
    }
}
