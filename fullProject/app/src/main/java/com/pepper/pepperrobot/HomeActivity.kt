package com.pepper.pepperrobot

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.widget.Button
import androidx.appcompat.app.AppCompatActivity

// QiSDK Imports
import com.aldebaran.qi.sdk.QiContext
import com.aldebaran.qi.sdk.QiSDK
import com.aldebaran.qi.sdk.RobotLifecycleCallbacks
import com.aldebaran.qi.sdk.builder.AnimateBuilder
import com.aldebaran.qi.sdk.builder.AnimationBuilder
import com.aldebaran.qi.sdk.builder.SayBuilder
import com.aldebaran.qi.sdk.`object`.conversation.BodyLanguageOption

class HomeActivity : AppCompatActivity(), RobotLifecycleCallbacks {

    private var qiContext: QiContext? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)

        // Register the robot to enable touch sensors on the Home Screen
        QiSDK.register(this, this)

        // Setup Buttons to switch to MainActivity (Tasks)
        findViewById<Button>(R.id.btn_chat).setOnClickListener { startRobotMode("CHAT") }
        findViewById<Button>(R.id.btn_follow).setOnClickListener { startRobotMode("FOLLOW") }
        findViewById<Button>(R.id.btn_expo).setOnClickListener { startRobotMode("EXPO") }
        findViewById<Button>(R.id.btn_corridor).setOnClickListener { startRobotMode("CORRIDOR") }
        findViewById<Button>(R.id.btn_petra).setOnClickListener { startRobotMode("PETRA") }
    }

    override fun onDestroy() {
        QiSDK.unregister(this, this)
        super.onDestroy()
    }

    private fun startRobotMode(mode: String) {
        // When we start a new activity, HomeActivity pauses/stops.
        // This automatically stops the touch listeners defined here.
        val intent = Intent(this, MainActivity::class.java)
        intent.putExtra("ROBOT_MODE", mode)
        startActivity(intent)
    }

    // =============================================================
    //               ROBOT LIFECYCLE (IDLE MODE)
    // =============================================================

    override fun onRobotFocusGained(qiContext: QiContext) {
        this.qiContext = qiContext
        Log.i("AneesHome", "Robot Focus Gained - Ready for Touch")

        // Activate Touch Sensors
        setupTouchSensors(qiContext)
    }

    override fun onRobotFocusLost() {
        this.qiContext = null
        Log.i("AneesHome", "Robot Focus Lost - Stopping Touch Reactions")
    }

    override fun onRobotFocusRefused(reason: String) {
        Log.e("AneesHome", "Focus Refused: $reason")
    }

    // =============================================================
    //                  TOUCH SENSORS LOGIC
    // =============================================================

    private fun setupTouchSensors(qiContext: QiContext) {
        val touchService = qiContext.touch

        // 1. Left Hand Sensor
        touchService.async().getSensor("LHand/Touch/Back").thenConsume { f ->
            if (f.isSuccess) {
                f.get().addOnStateChangedListener { s ->
                    if (s.touched) performLeftHandReaction(qiContext)
                }
            } else {
                Log.e("AneesHome", "Error getting Left Hand sensor: ${f.errorMessage}")
            }
        }

        // 2. Right Hand Sensor
        touchService.async().getSensor("RHand/Touch/Back").thenConsume { f ->
            if (f.isSuccess) {
                f.get().addOnStateChangedListener { s ->
                    if (s.touched) performRightHandReaction(qiContext)
                }
            } else {
                Log.e("AneesHome", "Error getting Right Hand sensor: ${f.errorMessage}")
            }
        }

        // 3. Head Sensor
        touchService.async().getSensor("Head/Touch/Middle").thenConsume { f ->
            if (f.isSuccess) {
                f.get().addOnStateChangedListener { s ->
                    if (s.touched) performHeadReaction(qiContext)
                }
            } else {
                Log.e("AneesHome", "Error getting Head sensor: ${f.errorMessage}")
            }
        }
    }

    // =============================================================
    //                  REACTION ANIMATIONS
    // =============================================================

    private fun performLeftHandReaction(qiContext: QiContext) {
        Thread {
            try {
                Log.i("AneesHome", "Left Hand Touched - Playing Animation")

                // 1. Check Hand
                val animCheck = AnimationBuilder.with(qiContext).withResources(R.raw.check_left_01).build()
                AnimateBuilder.with(qiContext).withAnimation(animCheck).build().run()

                // 2. Look at hand & Speak
                val animLook = AnimateBuilder.with(qiContext)
                    .withAnimation(AnimationBuilder.with(qiContext).withResources(R.raw.look_hand_left_01).build())
                    .build()
                val sayDont = SayBuilder.with(qiContext)
                    .withText("Please don't touch me")
                    .withBodyLanguageOption(BodyLanguageOption.DISABLED)
                    .build()

                // Run Look & Speak in parallel
                val f1 = animLook.async().run()
                val f2 = sayDont.async().run()
                f1.get(); f2.get()

                // 3. Make Space
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

            } catch (e: Exception) {
                Log.e("AneesHome", "Left Hand Anim Error: ${e.message}")
                say(qiContext, "Hey, please don't touch my hand.")
            }
        }.start()
    }

    private fun performRightHandReaction(qiContext: QiContext) {
        Thread {
            try {
                Log.i("AneesHome", "Right Hand Touched - Playing Animation")

                val animCheck = AnimationBuilder.with(qiContext).withResources(R.raw.check_right_01).build()
                AnimateBuilder.with(qiContext).withAnimation(animCheck).build().run()

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

            } catch (e: Exception) {
                Log.e("AneesHome", "Right Hand Anim Error: ${e.message}")
                say(qiContext, "Hey, please don't touch my hand.")
            }
        }.start()
    }

    private fun performHeadReaction(qiContext: QiContext) {
        Thread {
            try {
                Log.i("AneesHome", "Head Touched - Playing Animation")

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
            } catch (e: Exception) {
                Log.e("AneesHome", "Hoead Anim Error: ${e.message}")
                say(qiContext, "Hey, please don't touch my head.")
            }
        }.start()
    }

    private fun say(qiContext: QiContext, text: String) {
        try {
            SayBuilder.with(qiContext).withText(text).build().run()
        } catch (e: Exception) {
            Log.e("AneesHome", "Say error: ${e.message}")
        }
    }
}