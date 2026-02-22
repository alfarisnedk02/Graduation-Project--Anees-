Installation & Environment Setup
Setting up the development environment for Pepper (NAOqi 2.9) requires strict adherence to specific legacy versions to avoid the known software incompatibilities.

1. Android Studio & SDK Configuration

Mandatory Version: You must use Android Studio 4.2.2 (released in 2021). Newer versions trigger internal API mismatches.

QiSDK Plugin: Install the QiSDK plugin within this specific Android Studio version to enable Pepper-specific libraries.

Java Versioning: Ensure that the Java version is consistent across both the Project Gradle and App Gradle modules to prevent build failures.

2. Resolving Gradle Sync & Certification Errors
If you encounter the "unable to find valid certification path" error:

Maven Central: Ensure mavenCentral() is correctly configured in your build.gradle files.

SSL Certificates: This error often occurs when the IDE cannot verify the connection to the repository. You may need to manually import the repository's SSL certificate into your Java KeyStore (cacerts) or ensure your system clock is synchronized.

3. Emulator & Virtualization Fixes
The QiSDK emulator is highly sensitive to modern system configurations.

Disable Hyper-V: The emulator depends on Intel HAXM, which is incompatible with Windows Hyper-V. You must disable Hyper-V (which will temporarily disable Docker and WSL2) to allow the virtual robot to boot.


Graphics Drivers: If the emulator crashes on startup, it is likely due to an OpenGL conflict with modern NVIDIA/AMD drivers. Try lowering the hardware acceleration settings within the Android Virtual Device (AVD) manager.

🚫 Why We Avoid Choregraphe and Python SDK
While these tools are common in older Pepper tutorials, they are avoided in this project for the following reasons:


Choregraphe: Incompatible with NAOqi 2.9; it fails to find critical services like ALBehaviorManager on newer Android-based robots.


Python SDK: Prevents the use of the chest tablet, meaning no interactive buttons or images can be displayed. It also prevents the robot from running as a standalone app.

<img width="2245" height="3179" alt="FinalPoster" src="https://github.com/user-attachments/assets/deb948a3-fc75-4065-a9b3-d2b12fedd8f5" />

