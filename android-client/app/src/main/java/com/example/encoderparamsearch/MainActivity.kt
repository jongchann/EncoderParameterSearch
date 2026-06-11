package com.example.encoderparamsearch

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val backendUrl = EditText(this).apply {
            hint = "Backend URL"
            setText("http://10.0.2.2:8000")
            singleLine()
        }
        val sessionId = EditText(this).apply {
            hint = "Session ID"
            singleLine()
        }
        val mockMode = CheckBox(this).apply {
            text = "Mock mode"
            isChecked = true
        }
        val status = TextView(this).apply {
            text = "Ready"
        }
        val result = TextView(this).apply {
            text = "No result yet"
            setTextIsSelectable(true)
        }
        val registerButton = Button(this).apply {
            text = "Register capability"
        }
        val createSessionButton = Button(this).apply {
            text = "Create session"
        }
        val runTrialButton = Button(this).apply {
            text = "Run one trial"
        }

        createSessionButton.setOnClickListener {
            runClientAction(status, result, "Session created") {
                val response = client(backendUrl, mockMode).createSession()
                val createdSessionId = response.getString("session_id")
                mainHandler.post {
                    sessionId.setText(createdSessionId)
                }
                response
            }
        }
        registerButton.setOnClickListener {
            runClientAction(status, result, "Capability registered") {
                client(backendUrl, mockMode).registerCapability(sessionId.text.toString())
            }
        }
        runTrialButton.setOnClickListener {
            runClientAction(status, result, "Trial completed") {
                client(backendUrl, mockMode).runOneTrial(
                    sessionId.text.toString(),
                    defaultTrialSource(),
                )
            }
        }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 32)
            addView(backendUrl, fullWidthParams())
            addView(mockMode, fullWidthParams())
            addView(sessionId, fullWidthParams())
            addView(createSessionButton, fullWidthParams())
            addView(registerButton, fullWidthParams())
            addView(runTrialButton, fullWidthParams())
            addView(status, fullWidthParams())
            addView(result, fullWidthParams())
        }
        setContentView(layout)
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun client(backendUrl: EditText, mockMode: CheckBox): AppClient {
        return if (mockMode.isChecked) {
            MockAppClient()
        } else {
            NetworkAppClient(backendUrl.text.toString())
        }
    }

    private fun defaultTrialSource(): TrialSource {
        val width = 1280
        val height = 720
        val frameRate = 30
        val durationSec = 2
        return TrialSource(
            width = width,
            height = height,
            frameRate = frameRate,
            durationSec = durationSec,
            encoder = SyntheticSurfaceSourceEncoder(width, height, frameRate, durationSec),
        )
    }

    private fun runClientAction(
        status: TextView,
        result: TextView,
        successMessage: String,
        action: () -> JSONObject,
    ) {
        status.text = "Running..."
        executor.execute {
            val outcome = try {
                val response = action()
                ActionOutcome(successMessage, response.toString(2))
            } catch (error: Exception) {
                ActionOutcome(
                    "Failed",
                    error.message ?: error.javaClass.simpleName,
                )
            }
            mainHandler.post {
                status.text = outcome.status
                result.text = outcome.detail
            }
        }
    }

    private fun fullWidthParams(): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        )
    }
}

data class ActionOutcome(
    val status: String,
    val detail: String,
)
