package com.example.encoderparamsearch

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
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
        val status = TextView(this).apply {
            text = "Ready"
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
            runClientAction(status) {
                val response = BackendClient(backendUrl.text.toString()).createSession()
                val createdSessionId = response.getString("session_id")
                mainHandler.post {
                    sessionId.setText(createdSessionId)
                }
                "Session created: $createdSessionId"
            }
        }
        registerButton.setOnClickListener {
            runClientAction(status) {
                client(backendUrl).registerCapability(sessionId.text.toString())
                "Capability registered"
            }
        }
        runTrialButton.setOnClickListener {
            runClientAction(status) {
                val runner = client(backendUrl)
                val response = runner.runOneTrial(sessionId.text.toString(), defaultTrialSource())
                "Trial uploaded: ${response.optString("status", "ok")}"
            }
        }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 32)
            addView(backendUrl, fullWidthParams())
            addView(sessionId, fullWidthParams())
            addView(createSessionButton, fullWidthParams())
            addView(registerButton, fullWidthParams())
            addView(runTrialButton, fullWidthParams())
            addView(status, fullWidthParams())
        }
        setContentView(layout)
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun client(backendUrl: EditText): TrialRunner {
        return TrialRunner(
            BackendClient(backendUrl.text.toString()),
            CapabilityReporter(),
            EncoderParameterProxy(),
        )
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

    private fun runClientAction(status: TextView, action: () -> String) {
        status.text = "Running..."
        executor.execute {
            val message = try {
                action()
            } catch (error: Exception) {
                "Failed: ${error.message ?: error.javaClass.simpleName}"
            }
            mainHandler.post {
                status.text = message
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
