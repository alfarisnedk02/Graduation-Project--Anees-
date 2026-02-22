package com.pepper.pepperrobot

import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import android.util.Log
import android.view.View
import android.webkit.WebView
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

// CORE QiSDK
import com.aldebaran.qi.Future
import com.aldebaran.qi.sdk.QiContext
import com.aldebaran.qi.sdk.QiSDK
import com.aldebaran.qi.sdk.RobotLifecycleCallbacks

// BUILDERS
import com.aldebaran.qi.sdk.builder.*

// CLEAN IMPORTS
import com.aldebaran.qi.sdk.`object`.actuation.*
import com.aldebaran.qi.sdk.`object`.geometry.*
import com.aldebaran.qi.sdk.`object`.conversation.*
import com.aldebaran.qi.sdk.`object`.locale.*
import com.aldebaran.qi.sdk.`object`.touch.*

// NETWORKING
import okhttp3.MediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import org.json.JSONObject
import org.json.JSONArray
import java.util.concurrent.TimeUnit
import java.util.UUID

class MainActivity : AppCompatActivity(), RobotLifecycleCallbacks {

    private lateinit var statusText: TextView
    private lateinit var logText: TextView
    private lateinit var inputField: EditText
    private lateinit var btnSend: Button
    private lateinit var btnMic: Button
    private lateinit var btnHome: Button
    private lateinit var layoutInputArea: LinearLayout

    // Trackers
    private var currentChatFuture: Future<Void>? = null
    private var currentGoToFuture: Future<Void>? = null

    // --- FLAGS FOR TOGGLE BEHAVIOR ---
    private var isListening = false
    private var isPetraSessionRunning = false
    private var isFollowing = false

    // Current Mode
    private var activeMode = "CHAT"
    private var qiContext: QiContext? = null

    // Flag for First Interaction
    private var isFirstRagInteraction = true

    // --- RETRY COUNTER ---
    private var pathRetries = 0

    // --- SERVER CONFIGURATION ---
    private var userId: String? = null

    // Point to your Python API Endpoint
    private val RAG_SERVER_URL = "http://192.168.8.99:8000/chat"

    private val OPENAI_API_KEY = "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"
    private val OPENAI_URL = "https://api.openai.com/v1/chat/completions"

    private val client = OkHttpClient.Builder()
        .connectTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    // --- CORRIDOR PATH VARIABLES ---
    private val rawPathInstructions = listOf(
        "M 1.365", "L", "M 4.095", "L", "M 1.365", "R", "M 2.475", "R",
        "M 13.65", "L", "M 0.6825", "L", "M 32.76", "L", "M 7.965", "R",
        "M 2.73", "R", "M 7.735", "L", "M 20.475", "L", "M 21.385", "R",
        "M 0.455", "R", "M 21.385", "R", "M 43.225", "R", "M 2.93", "L",
        "M 1.365", "R", "M 4.095", "R", "M 1.365"
    )
    private val calculatedWaypoints = ArrayList<PathPoint>()
    private var currentWaypointIndex = 0

    // --- EXPO PATH VARIABLES ---
    private val rawExpoPathInstructions = listOf(
        "M 11.25", "L",
        "M 7.65", "L",
        "M 4.05", "R",
        "M 3.6", "L",
        "M 4.05", "L",
        "M 11.25", "R",
        "M 3.15"
    )
    private val calculatedExpoWaypoints = ArrayList<PathPoint>()
    private var currentExpoIndex = 0

    // --- PHOTO POSE RESOURCES ---
    private val photoPoses = listOf(
        R.raw.pose_left_01, R.raw.pose_left_02, R.raw.pose_left_03, R.raw.pose_left_04,
        R.raw.pose_right_01, R.raw.pose_right_02, R.raw.pose_right_03, R.raw.pose_right_04
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.tv_status)
        logText = findViewById(R.id.tv_log)
        inputField = findViewById(R.id.et_input)
        btnSend = findViewById(R.id.btn_send)
        btnMic = findViewById(R.id.btn_mic)
        btnHome = findViewById(R.id.btn_home)
        layoutInputArea = findViewById(R.id.layout_input_area)

        // --- 1. LOAD USER ID FROM STORAGE ---
        val prefs = getSharedPreferences("PepperAppPrefs", Context.MODE_PRIVATE)
        userId = prefs.getString("user_id", null)

        if (userId != null) {
            Log.i("Pepper", "Loaded existing User ID: $userId")
        } else {
            Log.i("Pepper", "No User ID yet. Waiting for server handshake.")
        }

        activeMode = intent.getStringExtra("ROBOT_MODE") ?: "CHAT"
        val displayId = userId?.takeLast(4) ?: "None"
        updateStatus("Mode: $activeMode | ID: $displayId")

        if (activeMode == "CORRIDOR" || activeMode == "EXPO" || activeMode == "FOLLOW") {
            layoutInputArea.visibility = View.GONE
        } else {
            layoutInputArea.visibility = View.VISIBLE
        }

        btnHome.setOnClickListener {
            forceStopEverything()
            finish()
        }

        // --- 2. LONG CLICK TO START NEW SESSION (Reset ID) ---
        btnHome.setOnLongClickListener {
            val p = getSharedPreferences("PepperAppPrefs", Context.MODE_PRIVATE)
            p.edit().remove("user_id").apply()
            userId = null
            isFirstRagInteraction = true
            addToLog("System: New Session Started (Memory Cleared).")
            updateStatus("Mode: $activeMode | ID: None")
            if(qiContext != null) sayBlocking(qiContext!!, "I have reset my memory. Ready for a new user.")
            true
        }

        btnSend.setOnClickListener {
            val text = inputField.text.toString()
            if (text.isEmpty() || qiContext == null) return@setOnClickListener

            addToLog("Me: $text")
            inputField.setText("")

            stopChatSafely()

            if (isFirstRagInteraction) {
                isFirstRagInteraction = false
            }

            checkAndAnimateGreeting(qiContext!!, text)

            if (activeMode == "PETRA") askOpenAI(qiContext!!, text)
            else askRAGServer(qiContext!!, text)
        }

        btnMic.setOnClickListener {
            if (qiContext != null) {
                if (activeMode == "PETRA") {
                    if (isPetraSessionRunning) {
                        isPetraSessionRunning = false
                        Thread {
                            stopChatSafely()
                            sayBlocking(qiContext!!, "Petra mode paused.")
                            updateStatus("Status: Petra Paused")
                        }.start()
                    } else {
                        isPetraSessionRunning = true
                        Thread {
                            startPetraLoop(qiContext!!)
                        }.start()
                    }
                } else {
                    if (isListening) {
                        isListening = false
                        Thread {
                            stopChatSafely()
                            sayBlocking(qiContext!!, "Listening stopped.")
                            updateStatus("Status: Mic Stopped")
                        }.start()
                    } else {
                        Thread {
                            if (isFirstRagInteraction) {
                                sayBlocking(qiContext!!, "Hi, I am Anees. How are you feeling?")
                                isFirstRagInteraction = false
                            }
                            listenOnce(qiContext!!)
                        }.start()
                    }
                }
            }
        }
        QiSDK.register(this, this)
    }

    override fun onDestroy() {
        QiSDK.unregister(this, this)
        super.onDestroy()
    }

    override fun onRobotFocusGained(qiContext: QiContext) {
        this.qiContext = qiContext
        val displayId = userId?.takeLast(4) ?: "None"
        updateStatus("Online ($activeMode) - ID: $displayId")
        setupTouchSensors(qiContext)

        when (activeMode) {
            "CHAT" -> addToLog("System: Press Mic to start.")
            "PETRA" -> {
                addToLog("System: Petra Mode.")
                say(qiContext, "Hello! Ask me about Petra University.")
            }
            "FOLLOW" -> {
                addToLog("System: Follow Mode.")
                say(qiContext, "I am following you.")
                isFollowing = true
                startFollowVoiceCommandLoop(qiContext)
                startHumanTrackingLoop(qiContext)
            }
            "CORRIDOR" -> {
                addToLog("System: Starting Corridor logic...")
                startCorridorPatrol(qiContext)
            }
            "EXPO" -> {
                addToLog("System: Starting Expo logic...")
                startExpoPatrol(qiContext)
            }
        }
    }

    override fun onRobotFocusLost() {
        this.qiContext = null
        updateStatus("Status: Focus Lost")
        forceStopEverything()
    }

    override fun onRobotFocusRefused(reason: String) {
        updateStatus("Status: Refused ($reason)")
    }

    private fun forceStopEverything() {
        isPetraSessionRunning = false
        isListening = false
        isFollowing = false
        stopChatSafely()
        currentGoToFuture?.requestCancellation()
        updateStatus("Status: Stopped")
    }

    private fun stopChatSafely() {
        try {
            if (currentChatFuture != null) {
                currentChatFuture?.requestCancellation()
                currentChatFuture?.get(500, TimeUnit.MILLISECONDS)
            }
        } catch (e: Exception) {
            // Ignore
        } finally {
            currentChatFuture = null
        }
    }

    // =============================================================
    //                  GREETING & CHAT
    // =============================================================
    private fun checkAndAnimateGreeting(qiContext: QiContext, text: String) {
        val lower = text.lowercase()
        if (lower.contains("hi") || lower.contains("hello") || lower.contains("hey")) {
            Thread {
                try {
                    val animation = AnimationBuilder.with(qiContext)
                        .withResources(R.raw.hello_10)
                        .build()
                    val animate = AnimateBuilder.with(qiContext)
                        .withAnimation(animation)
                        .build()
                    animate.async().run()
                } catch (e: Exception) {
                    Log.e("Pepper", "Anim failed: ${e.message}")
                }
            }.start()
        }
    }

    private fun listenOnce(qiContext: QiContext) {
        stopChatSafely()
        isListening = true

        val locale = Locale(Language.ENGLISH, Region.UNITED_STATES)
        val topic = TopicBuilder.with(qiContext).withResource(R.raw.commands).build()
        val qiChatbot = QiChatbotBuilder.with(qiContext).withTopic(topic).withLocale(locale).build()
        val chat = ChatBuilder.with(qiContext).withChatbot(qiChatbot).withLocale(locale).build()

        chat.addOnStartedListener { updateStatus("Status: Listening...") }

        val inputVar = qiChatbot.variable("input")
        inputVar.addOnValueChangedListener { input ->
            if (input.trim().isNotEmpty()) {
                inputVar.async().setValue("")
                addToLog("Heard: '$input'")

                stopChatSafely()

                checkAndAnimateGreeting(qiContext, input)
                askRAGServer(qiContext, input)
            }
        }
        currentChatFuture = chat.async().run()
        currentChatFuture?.thenConsume { isListening = false }
    }

    // =============================================================
    //                  UPDATED RAG SERVER FUNCTION (WITH PDF)
    // =============================================================
    private fun askRAGServer(qiContext: QiContext, userText: String) {
        val thread = Thread {
            var sessionFinished = false
            try {
                val jsonBody = JSONObject()
                jsonBody.put("message", userText)

                if (userId != null) {
                    jsonBody.put("user_id", userId)
                }

                val request = Request.Builder()
                    .url(RAG_SERVER_URL)
                    .post(RequestBody.create(MediaType.parse("application/json"), jsonBody.toString()))
                    .build()

                val response = client.newCall(request).execute()

                if (response.isSuccessful) {
                    val responseStr = response.body()?.string()
                    if (responseStr != null) {
                        val jsonResponse = JSONObject(responseStr)

                        if (jsonResponse.has("user_id")) {
                            userId = jsonResponse.getString("user_id")
                            val prefs = getSharedPreferences("PepperAppPrefs", Context.MODE_PRIVATE)
                            prefs.edit().putString("user_id", userId).apply()
                            Log.i("Pepper", "Server assigned User ID: $userId")
                            val displayId = userId?.takeLast(4) ?: "..."
                            updateStatus("Active - ID: $displayId")
                        }

                        val botResponse = jsonResponse.optString("response", "...")
                        val isFinished = jsonResponse.optBoolean("is_finished", false)
                        val finalReport = jsonResponse.optString("final_report", "")
                        val optionsArray = jsonResponse.optJSONArray("options")

                        // --- NEW: PDF Parsing ---
                        val pdfData = jsonResponse.optJSONObject("pdf_data")

                        addToLog("Anees: $botResponse")
                        sayBlocking(qiContext, botResponse)

                        if (optionsArray != null && optionsArray.length() > 0) {
                            for (i in 0 until optionsArray.length()) {
                                val optionText = optionsArray.getString(i)
                                Thread.sleep(300)
                                sayBlocking(qiContext, optionText)
                            }
                        }

                        // --- NEW: PDF Handling ---
                        if (pdfData != null) {
                            // Extract PDF Data
                            val pdfUrl = pdfData.optString("pdf_url")
                            val qrImage = pdfData.optString("qr_image")
                            val htmlContent = pdfData.optString("html_content")

                            addToLog("PDF Generated successfully.")
                            sayBlocking(qiContext, "I have generated a PDF report for you. Please see the tablet.")

                            // Trigger UI on Main Thread
                            runOnUiThread {
                                showPdfOptions(pdfUrl, qrImage, htmlContent)
                            }
                        }

                        if (isFinished) {
                            sessionFinished = true
                            if (finalReport.isNotEmpty()) {
                                addToLog("FINAL REPORT:\n$finalReport")
                                sayBlocking(qiContext, "I have generated your summary. Thank you.")
                            } else {
                                sayBlocking(qiContext, "Session complete. Take care.")
                            }
                        }
                    }
                } else {
                    sayBlocking(qiContext, "Server Error: ${response.code()}")
                }
            } catch (e: Exception) {
                Log.e("Pepper", "Connection failed: ${e.message}")
                sayBlocking(qiContext, "I lost connection to the server.")
            } finally {
                if (!sessionFinished && activeMode == "CHAT") {
                    Thread.sleep(2000)
                    listenOnce(qiContext)
                } else {
                    isListening = false
                    updateStatus("Status: Session Ended")
                }
            }
        }
        thread.start()
    }

    // =============================================================
    //              NEW UI HELPER FUNCTIONS FOR PDF
    // =============================================================

    private fun showPdfOptions(pdfUrl: String, qrBase64: String, htmlContent: String) {
        val dialog = AlertDialog.Builder(this)
            .setTitle("Report Generated!")
            .setMessage("Your assessment report has been generated. Choose an option:")
            .setPositiveButton("View Online") { _, _ ->
                // Open PDF in browser
                try {
                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(pdfUrl))
                    startActivity(intent)
                } catch (e: Exception) {
                    addToLog("Error opening PDF: ${e.message}")
                }
            }
            .setNegativeButton("Show QR Code") { _, _ ->
                showQrCode(qrBase64)
            }
            .setNeutralButton("View Preview") { _, _ ->
                showHtmlPreview(htmlContent)
            }
            .create()

        dialog.show()
    }

    private fun showQrCode(base64Qr: String) {
        try {
            // Decode base64 and show QR code
            val decodedString = Base64.decode(base64Qr, Base64.DEFAULT)
            val bitmap = BitmapFactory.decodeByteArray(decodedString, 0, decodedString.size)

            val dialog = AlertDialog.Builder(this)
                .setTitle("Scan to Download Report")
                .setMessage("Scan this QR code with your phone to download the PDF report")
                .setView(ImageView(this).apply {
                    setImageBitmap(bitmap)
                    scaleType = ImageView.ScaleType.FIT_CENTER
                })
                .setPositiveButton("OK", null)
                .create()

            dialog.show()
        } catch (e: Exception) {
            addToLog("QR Error: ${e.message}")
        }
    }

    private fun showHtmlPreview(htmlContent: String) {
        // Create a WebView to show HTML preview
        val webView = WebView(this)
        webView.loadData(htmlContent, "text/html", "UTF-8")

        val dialog = AlertDialog.Builder(this)
            .setTitle("Report Preview")
            .setView(webView)
            .setPositiveButton("OK", null)
            .create()

        dialog.show()
    }

    // =============================================================
    //                  GENERIC HELPERS
    // =============================================================

    private fun sayBlocking(qiContext: QiContext, text: String) {
        try {
            SayBuilder.with(qiContext).withText(text).build().run()
        } catch (e: Exception) {
            Log.e("Pepper", "Say Error: ${e.message}")
        }
    }

    private fun say(qiContext: QiContext, text: String) {
        SayBuilder.with(qiContext).withText(text).build().async().run()
    }

    // =============================================================
    //                  PETRA MODE
    // =============================================================
    private fun startPetraLoop(qiContext: QiContext) {
        if (!isPetraSessionRunning) return
        stopChatSafely()
        val locale = Locale(Language.ENGLISH, Region.UNITED_STATES)
        val topic = TopicBuilder.with(qiContext).withResource(R.raw.commands).build()
        val qiChatbot = QiChatbotBuilder.with(qiContext).withTopic(topic).withLocale(locale).build()
        val chat = ChatBuilder.with(qiContext).withChatbot(qiChatbot).withLocale(locale).build()
        chat.addOnStartedListener { updateStatus("Status: Listening (Auto)...") }
        val inputVar = qiChatbot.variable("input")
        inputVar.addOnValueChangedListener { input ->
            if (input.isNotEmpty()) {
                inputVar.async().setValue("")
                addToLog("Me: $input")
                stopChatSafely()
                val lowerInput = input.lowercase()
                if (lowerInput.contains("picture") || lowerInput.contains("photo") || lowerInput.contains("selfie")) {
                    takePicturePose(qiContext)
                } else {
                    checkAndAnimateGreeting(qiContext, input)
                    askOpenAI(qiContext, input)
                }
            }
        }
        currentChatFuture = chat.async().run()
    }

    private fun takePicturePose(qiContext: QiContext) {
        Thread {
            try {
                if (!isPetraSessionRunning) return@Thread
                sayBlocking(qiContext, "Oh, a selfie? Sure! Get ready.")
                Thread.sleep(1500)
                sayBlocking(qiContext, "3")
                Thread.sleep(1000)
                sayBlocking(qiContext, "2")
                Thread.sleep(1000)
                sayBlocking(qiContext, "1")
                val randomPoseRes = photoPoses.random()
                addToLog("System: Striking pose...")
                val animation = AnimationBuilder.with(qiContext).withResources(randomPoseRes).build()
                val animate = AnimateBuilder.with(qiContext).withAnimation(animation).build()
                animate.async().run().get()
                sayBlocking(qiContext, "That was fun!")
            } catch (e: Exception) {
                addToLog("Pose Error: ${e.message}")
                say(qiContext, "I couldn't find my pose file.")
            } finally {
                if (isPetraSessionRunning) startPetraLoop(qiContext)
            }
        }.start()
    }

    private fun askOpenAI(qiContext: QiContext, userText: String) {
        val thread = Thread {
            try {
                val sys = "You are an expert for Petra University (Jordan). Be concise."
                val json = JSONObject().put("model", "gpt-4o-mini").put("messages", JSONArray().put(JSONObject().put("role", "system").put("content", sys)).put(JSONObject().put("role", "user").put("content", userText)))
                val req = Request.Builder().url(OPENAI_URL).addHeader("Authorization", "Bearer $OPENAI_API_KEY").post(RequestBody.create(MediaType.parse("application/json"), json.toString())).build()
                val res = client.newCall(req).execute()
                if (res.isSuccessful) {
                    val responseStr = res.body()?.string()
                    if (responseStr != null) {
                        val ans = JSONObject(responseStr).getJSONArray("choices").getJSONObject(0).getJSONObject("message").getString("content")
                        addToLog("Pepper: $ans")
                        sayBlocking(qiContext, ans)
                    }
                } else {
                    val errCode = res.code()
                    addToLog("AI Error Code: $errCode")
                    sayBlocking(qiContext, "I had a problem connecting.")
                }
            } catch (e: Exception) {
                addToLog("Net Error: ${e.message}")
                sayBlocking(qiContext, "I can't reach the internet.")
            }
            finally {
                Thread.sleep(1000)
                if (isPetraSessionRunning) startPetraLoop(qiContext)
            }
        }
        thread.start()
    }

    // =============================================================
    //                  CORRIDOR PATROL
    // =============================================================
    private var homeFrame: FreeFrame? = null

    private fun startCorridorPatrol(qiContext: QiContext) {
        calculateCoordinates()
        val robotFrame = qiContext.actuation.robotFrame()
        val mapping = qiContext.mapping
        val t = System.currentTimeMillis()
        val transform = robotFrame.computeTransform(robotFrame).transform
        homeFrame = mapping.makeFreeFrame()
        homeFrame?.update(robotFrame, transform, t)
        addToLog("System: Corridor Patrol in 3s...")
        say(qiContext, "Starting patrol in 3 seconds.")
        Thread {
            Thread.sleep(3000)
            currentWaypointIndex = 0
            executeNextWaypoint(qiContext)
        }.start()
    }

    private fun calculateCoordinates() {
        calculatedWaypoints.clear()
        var currentX = 0.0
        var currentY = 0.0
        var currentHeading = 0
        for (instruction in rawPathInstructions) {
            when {
                instruction == "L" -> currentHeading += 90
                instruction == "R" -> currentHeading -= 90
                instruction.startsWith("M") -> {
                    val distance = instruction.substring(2).toDouble()
                    val normalizedHeading = (currentHeading % 360 + 360) % 360
                    var directionDesc = "Forward"
                    if (normalizedHeading == 90) directionDesc = "Left"
                    if (normalizedHeading == 270) directionDesc = "Right"
                    if (normalizedHeading == 180) directionDesc = "Back"
                    when (normalizedHeading) {
                        0 ->    currentX += distance
                        90 ->   currentY += distance
                        180 -> currentX -= distance
                        270 -> currentY -= distance
                    }
                    val theta = Math.toRadians(normalizedHeading.toDouble())
                    calculatedWaypoints.add(PathPoint(currentX, currentY, theta, directionDesc))
                }
            }
        }
    }

    private fun executeNextWaypoint(qiContext: QiContext) {
        if (currentWaypointIndex >= calculatedWaypoints.size) {
            say(qiContext, "Patrol finished.")
            addToLog("Patrol Complete.")
            return
        }
        val point = calculatedWaypoints[currentWaypointIndex]
        addToLog("Step ${currentWaypointIndex + 1}: ${point.desc} -> (${String.format("%.2f", point.x)}, ${String.format("%.2f", point.y)})")

        val transform = TransformBuilder.create().from2DTransform(point.x, point.y, point.theta)
        val baseFrame = homeFrame?.frame() ?: return
        val targetFrame = baseFrame.makeAttachedFrame(transform).frame()

        val lookAt = LookAtBuilder.with(qiContext).withFrame(targetFrame).build()
        lookAt.setPolicy(LookAtMovementPolicy.HEAD_ONLY)
        val currentLookAtFuture = lookAt.async().run()

        val goTo = GoToBuilder.with(qiContext).withFrame(targetFrame)
            .withPathPlanningPolicy(PathPlanningPolicy.GET_AROUND_OBSTACLES)
            .withMaxSpeed(0.35f)
            .build()

        currentGoToFuture = goTo.async().run()
        currentGoToFuture?.thenConsume { future ->
            if (future.isSuccess) {
                pathRetries = 0
                currentLookAtFuture.requestCancellation()
                currentWaypointIndex++
                executeNextWaypoint(qiContext)
            } else {
                pathRetries++
                addToLog("Blocked! Retry #$pathRetries")
                val specialStepsIndices = listOf(4, 5, 11, 12)
                if (specialStepsIndices.contains(currentWaypointIndex) && pathRetries >= 3) {
                    addToLog("Skipping step.")
                    say(qiContext, "Skipping.")
                    pathRetries = 0
                    currentLookAtFuture.requestCancellation()
                    currentWaypointIndex++
                    executeNextWaypoint(qiContext)
                } else {
                    handleBlockedPath(qiContext, currentLookAtFuture)
                }
            }
        }
    }

    private fun handleBlockedPath(qiContext: QiContext, lookAtFuture: Future<Void>) {
        currentGoToFuture?.requestCancellation()
        Thread.sleep(500)
        executeNextWaypoint(qiContext)
    }

    // =============================================================
    //                  EXPO PATROL
    // =============================================================
    private fun startExpoPatrol(qiContext: QiContext) {
        calculateExpoCoordinates()
        val robotFrame = qiContext.actuation.robotFrame()
        val mapping = qiContext.mapping
        val t = System.currentTimeMillis()
        val transform = robotFrame.computeTransform(robotFrame).transform
        homeFrame = mapping.makeFreeFrame()
        homeFrame?.update(robotFrame, transform, t)
        addToLog("System: Expo Patrol in 3s...")
        say(qiContext, "Starting Expo patrol in 3 seconds.")
        Thread {
            Thread.sleep(3000)
            currentExpoIndex = 0
            executeExpoNextWaypoint(qiContext)
        }.start()
    }

    private fun calculateExpoCoordinates() {
        calculatedExpoWaypoints.clear()
        var currentX = 0.0
        var currentY = 0.0
        var currentHeading = 0
        for (instruction in rawExpoPathInstructions) {
            when {
                instruction == "L" -> currentHeading += 90
                instruction == "R" -> currentHeading -= 90
                instruction.startsWith("M") -> {
                    val distance = instruction.substring(2).toDouble()
                    val normalizedHeading = (currentHeading % 360 + 360) % 360
                    var directionDesc = "Forward"
                    if (normalizedHeading == 90) directionDesc = "Left"
                    if (normalizedHeading == 270) directionDesc = "Right"
                    if (normalizedHeading == 180) directionDesc = "Back"
                    when (normalizedHeading) {
                        0 ->    currentX += distance
                        90 ->   currentY += distance
                        180 -> currentX -= distance
                        270 -> currentY -= distance
                    }
                    val theta = Math.toRadians(normalizedHeading.toDouble())
                    calculatedExpoWaypoints.add(PathPoint(currentX, currentY, theta, directionDesc))
                }
            }
        }
    }

    private fun executeExpoNextWaypoint(qiContext: QiContext) {
        if (currentExpoIndex >= calculatedExpoWaypoints.size) {
            say(qiContext, "Expo Patrol finished.")
            addToLog("Patrol Complete.")
            return
        }
        val point = calculatedExpoWaypoints[currentExpoIndex]
        addToLog("Expo Step ${currentExpoIndex + 1}: ${point.desc} -> (${String.format("%.2f", point.x)}, ${String.format("%.2f", point.y)})")

        val transform = TransformBuilder.create().from2DTransform(point.x, point.y, point.theta)
        val baseFrame = homeFrame?.frame() ?: return
        val targetFrame = baseFrame.makeAttachedFrame(transform).frame()

        val lookAt = LookAtBuilder.with(qiContext).withFrame(targetFrame).build()
        lookAt.setPolicy(LookAtMovementPolicy.HEAD_ONLY)
        val currentLookAtFuture = lookAt.async().run()

        val goTo = GoToBuilder.with(qiContext).withFrame(targetFrame)
            .withPathPlanningPolicy(PathPlanningPolicy.GET_AROUND_OBSTACLES)
            .withMaxSpeed(0.35f)
            .build()

        currentGoToFuture = goTo.async().run()
        currentGoToFuture?.thenConsume { future ->
            if (future.isSuccess) {
                pathRetries = 0
                currentLookAtFuture.requestCancellation()
                currentExpoIndex++
                executeExpoNextWaypoint(qiContext)
            } else {
                pathRetries++
                addToLog("Blocked! Retry #$pathRetries")
                if (pathRetries >= 3) {
                    addToLog("Skipping step.")
                    say(qiContext, "Skipping.")
                    pathRetries = 0
                    currentLookAtFuture.requestCancellation()
                    currentExpoIndex++
                    executeExpoNextWaypoint(qiContext)
                } else {
                    handleBlockedPath(qiContext, currentLookAtFuture, true)
                }
            }
        }
    }

    private fun handleBlockedPath(qiContext: QiContext, lookAtFuture: Future<Void>, isExpo: Boolean) {
        currentGoToFuture?.requestCancellation()
        Thread.sleep(500)
        if (isExpo) executeExpoNextWaypoint(qiContext)
        else executeNextWaypoint(qiContext)
    }

    // =============================================================
    //                  FOLLOW ME
    // =============================================================
    private fun startFollowVoiceCommandLoop(qiContext: QiContext) {
        currentChatFuture?.requestCancellation()
        val locale = Locale(Language.ENGLISH, Region.UNITED_STATES)
        val topic = TopicBuilder.with(qiContext).withResource(R.raw.commands).build()
        val qiChatbot = QiChatbotBuilder.with(qiContext).withTopic(topic).withLocale(locale).build()
        val chat = ChatBuilder.with(qiContext).withChatbot(qiChatbot).withLocale(locale).build()

        chat.addOnStartedListener { addToLog("Voice: Ready (Say 'Stop' to pause)") }

        val commandVar = qiChatbot.variable("command")
        commandVar.addOnValueChangedListener { command ->
            if (command.isNotEmpty()) {
                commandVar.async().setValue("")
                addToLog("Command: $command")
                if (command == "follow") {
                    isFollowing = true
                    say(qiContext, "Resuming follow.")
                }
                else if (command == "stop") {
                    isFollowing = false
                    stopMovement()
                    say(qiContext, "Stopped.")
                }
            }
        }
        currentChatFuture = chat.async().run()
    }

    private fun startHumanTrackingLoop(qiContext: QiContext) {
        val humanAwareness = qiContext.humanAwareness
        Thread {
            while (qiContext != null && activeMode == "FOLLOW") {
                val engagedHuman = humanAwareness.engagedHuman
                if (engagedHuman != null) {
                    val humanFrame = engagedHuman.headFrame
                    val lookAt = LookAtBuilder.with(qiContext).withFrame(humanFrame).build()
                    lookAt.setPolicy(LookAtMovementPolicy.HEAD_ONLY)
                    lookAt.async().run()
                    // IMMEDIATE FOLLOW CHECK
                    if (isFollowing) {
                        val robotFrame = qiContext.actuation.robotFrame()
                        val dist = Math.sqrt(
                            Math.pow(humanFrame.computeTransform(robotFrame).transform.translation.x, 2.0) +
                                    Math.pow(humanFrame.computeTransform(robotFrame).transform.translation.y, 2.0)
                        )
                        if (dist > 1.5) {
                            val target = humanFrame.makeAttachedFrame(TransformBuilder.create().fromXTranslation(1.0)).frame()
                            val goTo = GoToBuilder.with(qiContext).withFrame(target).withMaxSpeed(0.5f).build()
                            currentGoToFuture = goTo.async().run()
                            currentGoToFuture?.get()
                        }
                    }
                }
                Thread.sleep(200)
            }
        }.start()
    }

    // =============================================================
    //                  TOUCH SENSORS
    // =============================================================
    private fun setupTouchSensors(qiContext: QiContext) {
        val touchService = qiContext.touch
        touchService.async().getSensor("LHand/Touch/Back").thenConsume { f ->
            if (f.isSuccess) f.get().addOnStateChangedListener { s ->
                if (s.touched) { stopMovement(); performLeftHandReaction(qiContext) }
            }
        }
        touchService.async().getSensor("RHand/Touch/Back").thenConsume { f ->
            if (f.isSuccess) f.get().addOnStateChangedListener { s ->
                if (s.touched) { stopMovement(); performRightHandReaction(qiContext) }
            }
        }
        touchService.async().getSensor("Head/Touch/Middle").thenConsume { f ->
            if (f.isSuccess) f.get().addOnStateChangedListener { s ->
                if (s.touched) { stopMovement(); performHeadReaction(qiContext) }
            }
        }
    }

    private fun shouldTriggerTouchReaction(qiContext: QiContext): Boolean {
        val engagedHuman = qiContext.humanAwareness.engagedHuman
        if (engagedHuman == null) return true

        val robotFrame = qiContext.actuation.robotFrame()
        val humanFrame = engagedHuman.headFrame
        val transform = humanFrame.computeTransform(robotFrame).transform
        val x = transform.translation.x
        val y = transform.translation.y
        val distance = Math.sqrt(x*x + y*y)

        val isVeryClose = distance < 0.45
        val isFront = (x > 0.0) && (Math.abs(y) < x)

        return !isFront || isVeryClose
    }

    private fun performLeftHandReaction(qiContext: QiContext) {
        Thread {
            try {
                if (activeMode == "PETRA" || activeMode == "CHAT") return@Thread
                if (!shouldTriggerTouchReaction(qiContext)) return@Thread

                AnimateBuilder.with(qiContext)
                    .withAnimation(AnimationBuilder.with(qiContext).withResources(R.raw.check_left_01).build())
                    .build().run()

                val animLook = AnimateBuilder.with(qiContext)
                    .withAnimation(AnimationBuilder.with(qiContext).withResources(R.raw.look_hand_left_01).build())
                    .build()
                val sayDont = SayBuilder.with(qiContext)
                    .withText("Please don't touch me")
                    .withBodyLanguageOption(BodyLanguageOption.DISABLED)
                    .build()

                val f1 = animLook.async().run()
                val f2 = sayDont.async().run()
                f1.get(); f2.get()

                val animSpace = AnimateBuilder.with(qiContext)
                    .withAnimation(AnimationBuilder.with(qiContext).withResources(R.raw.make_space_01).build())
                    .build()
                val saySpace = SayBuilder.with(qiContext)
                    .withText("Please make space for me")
                    .withBodyLanguageOption(BodyLanguageOption.DISABLED)
                    .build()

                val f3 = animSpace.async().run()
                val f4 = saySpace.async().run()
                f3.get(); f4.get()

            } catch(e:Exception){
                addToLog("Anim Error: ${e.message}")
            }
        }.start()
    }

    private fun performRightHandReaction(qiContext: QiContext) {
        Thread {
            try {
                if (activeMode == "PETRA" || activeMode == "CHAT") return@Thread
                if (!shouldTriggerTouchReaction(qiContext)) return@Thread

                AnimateBuilder.with(qiContext)
                    .withAnimation(AnimationBuilder.with(qiContext).withResources(R.raw.check_right_01).build())
                    .build().run()

                val animLook = AnimateBuilder.with(qiContext)
                    .withAnimation(AnimationBuilder.with(qiContext).withResources(R.raw.look_hand_right_01).build())
                    .build()
                val sayDont = SayBuilder.with(qiContext)
                    .withText("Please don't touch me")
                    .withBodyLanguageOption(BodyLanguageOption.DISABLED)
                    .build()

                val f1 = animLook.async().run()
                val f2 = sayDont.async().run()
                f1.get(); f2.get()

                val animSpace = AnimateBuilder.with(qiContext)
                    .withAnimation(AnimationBuilder.with(qiContext).withResources(R.raw.make_space_01).build())
                    .build()
                val saySpace = SayBuilder.with(qiContext)
                    .withText("Please make space for me")
                    .withBodyLanguageOption(BodyLanguageOption.DISABLED)
                    .build()

                val f3 = animSpace.async().run()
                val f4 = saySpace.async().run()
                f3.get(); f4.get()

            } catch(e:Exception){
                addToLog("Anim Error: ${e.message}")
            }
        }.start()
    }

    private fun performHeadReaction(qiContext: QiContext) {
        Thread {
            try {
                if (activeMode == "PETRA" || activeMode == "CHAT") return@Thread
                if (!shouldTriggerTouchReaction(qiContext)) return@Thread

                val anim = AnimateBuilder.with(qiContext)
                    .withAnimation(AnimationBuilder.with(qiContext).withResources(R.raw.looking_around_wide_01).build())
                    .build()
                val say = SayBuilder.with(qiContext)
                    .withText("Heyyy that's not nice, please don't touch my head")
                    .withBodyLanguageOption(BodyLanguageOption.DISABLED)
                    .build()

                val f1 = anim.async().run()
                val f2 = say.async().run()
                f1.get(); f2.get()
            } catch(e:Exception){
                addToLog("Anim Error: ${e.message}")
            }
        }.start()
    }

    // --- GENERIC HELPERS ---
    private fun stopMovement() { currentGoToFuture?.requestCancellation() }
    private fun updateStatus(text: String) { runOnUiThread { statusText.text = text } }
    private fun addToLog(text: String) {
        runOnUiThread {
            val current = logText.text.toString()
            val lines = current.split("\n")
            val newText = if (lines.size > 8) lines.takeLast(8).joinToString("\n") else current
            logText.text = "$newText\n$text"
        }
    }
}

// DATA CLASS
data class PathPoint(
    val x: Double,
    val y: Double,
    val theta: Double, // Rotation in Radians
    val desc: String
)