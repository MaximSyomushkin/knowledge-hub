plugins {
    id("com.android.application")
}

android {
    namespace = "com.knowledgehub.tasks"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.knowledgehub.tasks"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}
