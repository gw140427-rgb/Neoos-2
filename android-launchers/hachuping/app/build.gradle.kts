plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "com.yangyang.hachupinglauncher"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.yangyang.hachupinglauncher"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }
}
