package com.neoos.launcher

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private val Navy = Color(0xFF080D18)
private val Panel = Color(0xFF111C2D)
private val Blue = Color(0xFF65BFFF)
private val Muted = Color(0xFFA6B5CA)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { NeoOSApp() }
    }
}

@Composable
private fun NeoOSApp() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val prefs = remember { context.getSharedPreferences("neoos_native", MODE_PRIVATE) }
    var endpoint by remember { mutableStateOf(prefs.getString("endpoint", "") ?: "") }
    var token by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("서버 주소를 설정한 뒤 연결 상태를 확인하세요.") }
    var result by remember { mutableStateOf("아직 서버에 연결하지 않았습니다.") }
    var busy by remember { mutableStateOf(false) }
    var tab by remember { mutableStateOf(0) }
    val scope = rememberCoroutineScope()

    suspend fun request(path: String): String = withContext(Dispatchers.IO) {
        val base = endpoint.trim().trimEnd('/')
        require(base.startsWith("https://")) { "HTTPS 주소를 입력해 주세요." }
        val conn = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10000
            readTimeout = 15000
            setRequestProperty("Accept", "application/json")
            if (token.isNotBlank()) setRequestProperty("Authorization", "Bearer ${token.trim()}")
        }
        try {
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) error("HTTP $code: ${body.take(500)}")
            body
        } finally { conn.disconnect() }
    }

    MaterialTheme(colorScheme = darkColorScheme(primary = Blue, background = Navy, surface = Panel)) {
        Column(
            Modifier.fillMaxSize().background(Navy).verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Spacer(Modifier.height(12.dp))
            Text("NEO OS", color = Color.White, fontSize = 32.sp, style = MaterialTheme.typography.headlineLarge)
            Text("NATIVE CONTROL CENTER", color = Blue, letterSpacing = 2.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = tab == 0, onClick = { tab = 0 }, label = { Text("대시보드") })
                FilterChip(selected = tab == 1, onClick = { tab = 1 }, label = { Text("연결 설정") })
            }
            if (tab == 0) {
                Card(colors = CardDefaults.cardColors(containerColor = Panel), shape = RoundedCornerShape(20.dp)) {
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("NeoOS 서버", color = Color.White, style = MaterialTheme.typography.titleLarge)
                        Text(if (endpoint.isBlank()) "서버 주소 미설정" else endpoint, color = Muted)
                        Text(status, color = Blue)
                        Button(
                            enabled = !busy && endpoint.isNotBlank(),
                            onClick = {
                                scope.launch {
                                    busy = true
                                    status = "서버 확인 중…"
                                    try {
                                        val body = request("/health")
                                        status = "연결 성공"
                                        result = body
                                    } catch (e: Exception) {
                                        status = "연결 실패: ${e.message ?: "알 수 없는 오류"}"
                                    } finally { busy = false }
                                }
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) { Text(if (busy) "확인 중…" else "서버 연결 확인") }
                    }
                }
                Card(colors = CardDefaults.cardColors(containerColor = Panel), shape = RoundedCornerShape(20.dp)) {
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("VPS 인스턴스", color = Color.White, style = MaterialTheme.typography.titleLarge)
                        Text("등록된 NeoOS 서버 목록을 API에서 불러옵니다.", color = Muted)
                        OutlinedButton(
                            enabled = !busy && endpoint.isNotBlank(),
                            onClick = {
                                scope.launch {
                                    busy = true
                                    try {
                                        val body = request("/api/instances")
                                        result = try {
                                            val json = JSONObject(body)
                                            json.toString(2)
                                        } catch (_: Exception) {
                                            try { JSONArray(body).toString(2) } catch (_: Exception) { body }
                                        }
                                        status = "VPS 목록을 불러왔습니다."
                                    } catch (e: Exception) {
                                        status = "목록 조회 실패: ${e.message ?: "오류"}"
                                    } finally { busy = false }
                                }
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) { Text("VPS 목록 새로고침") }
                    }
                }
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF050A12)), shape = RoundedCornerShape(14.dp)) {
                    Column(Modifier.fillMaxWidth().padding(14.dp)) {
                        Text("서버 응답", color = Blue)
                        Spacer(Modifier.height(8.dp))
                        Text(result, color = Muted, fontSize = 12.sp)
                    }
                }
            } else {
                Card(colors = CardDefaults.cardColors(containerColor = Panel), shape = RoundedCornerShape(20.dp)) {
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("API 연결 설정", color = Color.White, style = MaterialTheme.typography.titleLarge)
                        Text("NeoOS HTTPS API 주소를 입력하세요. 예: https://api.example.com", color = Muted)
                        OutlinedTextField(
                            value = endpoint, onValueChange = { endpoint = it },
                            modifier = Modifier.fillMaxWidth(), singleLine = true,
                            label = { Text("HTTPS 서버 주소") }
                        )
                        OutlinedTextField(
                            value = token, onValueChange = { token = it },
                            modifier = Modifier.fillMaxWidth(), singleLine = true,
                            label = { Text("Bearer 토큰 (선택)") }
                        )
                        Button(onClick = {
                            prefs.edit().putString("endpoint", endpoint.trim().trimEnd('/')).apply()
                            status = "서버 주소를 이 기기에 저장했습니다. 토큰은 저장하지 않습니다."
                            tab = 0
                        }, modifier = Modifier.fillMaxWidth()) { Text("주소 저장") }
                        Text("보안: 토큰은 앱을 닫으면 지워지며 기기에 저장하지 않습니다.", color = Muted, fontSize = 12.sp)
                    }
                }
            }
            Text("NeoOS Android Native · 앱 내부 화면은 Kotlin + Jetpack Compose로 구현", color = Muted, fontSize = 11.sp)
            Spacer(Modifier.height(24.dp))
        }
    }
}
