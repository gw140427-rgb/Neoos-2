package com.neoos.launcher

import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.View
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enterImmersiveMode()
        setContent { NeoOSScreen() }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) enterImmersiveMode()
    }

    private fun enterImmersiveMode() {
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            )
    }
}

@Composable
private fun NeoOSScreen() {
    val context = LocalContext.current
    val prefs = remember {
        context.getSharedPreferences("neoos_launcher", ComponentActivity.MODE_PRIVATE)
    }
    var vmPackage by remember { mutableStateOf(prefs.getString("vm_package", "") ?: "") }
    var termuxPackage by remember { mutableStateOf(prefs.getString("termux_package", "com.termux") ?: "com.termux") }
    var heybonPackage by remember { mutableStateOf(prefs.getString("heybon_package", "") ?: "") }
    var status by remember { mutableStateOf("모바일 환경 준비 완료") }

    fun launchPackage(packageName: String, label: String) {
        val cleaned = packageName.trim()
        if (cleaned.isEmpty()) {
            status = "$label 패키지 이름을 설정에서 입력해 주세요."
            return
        }
        try {
            val intent = Intent(Intent.ACTION_MAIN)
                .addCategory(Intent.CATEGORY_LAUNCHER)
                .setPackage(cleaned)
            context.startActivity(intent)
            status = "$label 실행 요청을 보냈습니다."
        } catch (_: ActivityNotFoundException) {
            status = "$label 앱을 찾지 못했습니다. 패키지 이름과 설치 상태를 확인해 주세요."
        } catch (_: SecurityException) {
            status = "$label 실행 권한이 없거나 앱에서 실행을 허용하지 않습니다."
        }
    }

    MaterialTheme(
        colorScheme = androidx.compose.material3.darkColorScheme(
            primary = Color(0xFF93C5FD),
            background = Color(0xFF080D18),
            surface = Color(0xFF111827)
        )
    ) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = Color(0xFF080D18)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 22.dp, vertical = 28.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Spacer(Modifier.height(24.dp))
                Text("NEO OS", fontSize = 38.sp, fontWeight = FontWeight.Black, color = Color.White)
                Text("MOBILE ENVIRONMENT", fontSize = 11.sp, letterSpacing = 3.sp, color = Color(0xFF93C5FD))
                Spacer(Modifier.height(28.dp))

                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(24.dp),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF172554))
                ) {
                    Column(Modifier.padding(20.dp)) {
                        Text("환영합니다", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.height(6.dp))
                        Text("NeoOS 통합 실행 화면입니다. 아래에서 설치된 환경을 실행하세요.", color = Color(0xFFDBEAFE))
                        Spacer(Modifier.height(16.dp))
                        Text(status, color = Color(0xFFBFDBFE), fontSize = 13.sp)
                    }
                }

                Spacer(Modifier.height(18.dp))
                EnvironmentCard("NeoOS VM", "가상 머신에 설치된 NeoOS 실행", vmPackage) {
                    launchPackage(vmPackage, "NeoOS VM")
                }
                EnvironmentCard("Termux", "터미널 환경 실행", termuxPackage) {
                    launchPackage(termuxPackage, "Termux")
                }
                EnvironmentCard("헤이본", "설정한 헤이본 앱 실행", heybonPackage) {
                    launchPackage(heybonPackage, "헤이본")
                }

                Spacer(Modifier.height(18.dp))
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF111827)),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(Modifier.padding(18.dp)) {
                        Text("환경 설정", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                        Spacer(Modifier.height(10.dp))
                        PackageField("NeoOS VM 패키지 이름", vmPackage) {
                            vmPackage = it
                            prefs.edit().putString("vm_package", it).apply()
                        }
                        PackageField("Termux 패키지 이름", termuxPackage) {
                            termuxPackage = it
                            prefs.edit().putString("termux_package", it).apply()
                        }
                        PackageField("헤이본 패키지 이름", heybonPackage) {
                            heybonPackage = it
                            prefs.edit().putString("heybon_package", it).apply()
                        }
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = {
                                try {
                                    context.startActivity(Intent(Settings.ACTION_HOME_SETTINGS))
                                } catch (_: Exception) {
                                    status = "기본 홈 앱 설정을 열 수 없습니다."
                                }
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text("NeoOS를 기본 홈 앱으로 설정")
                        }
                    }
                }
                Spacer(Modifier.height(18.dp))
                Text(
                    "자동 실행: Android 설정에서 NeoOS를 기본 홈 앱으로 선택하면 전원을 켠 뒤 홈 화면으로 NeoOS가 표시됩니다.",
                    color = Color(0xFF9CA3AF),
                    fontSize = 12.sp
                )
                Spacer(Modifier.height(30.dp))
            }
        }
    }
}

@Composable
private fun EnvironmentCard(
    title: String,
    description: String,
    packageName: String,
    onLaunch: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF111827))
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text(title, color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                Text(description, color = Color(0xFF9CA3AF), fontSize = 12.sp)
                if (packageName.isBlank()) {
                    Text("앱 패키지 설정 필요", color = Color(0xFFFBBF24), fontSize = 11.sp)
                }
            }
            Spacer(Modifier.width(8.dp))
            Button(onClick = onLaunch) { Text("실행") }
        }
    }
}

@Composable
private fun PackageField(label: String, value: String, onValueChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
    )
}
