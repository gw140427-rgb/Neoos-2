package com.yangyang.hachupinglauncher

import android.app.Activity
import android.os.Bundle
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.*
import android.content.pm.PackageManager

class MainActivity : Activity() {
    private val deepPink = Color.rgb(218, 74, 145)
    private lateinit var list: LinearLayout
    private lateinit var search: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.rgb(255, 226, 240)
        window.navigationBarColor = Color.rgb(255, 245, 250)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(18, 18, 18, 10)
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR,
                intArrayOf(Color.rgb(255, 237, 247), Color.rgb(255, 249, 253)))
        }
        root.addView(TextView(this).apply {
            text = "♡ 하츄핑 홈 ♡"
            textSize = 29f
            setTextColor(deepPink)
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            setPadding(8, 12, 8, 4)
        }, LinearLayout.LayoutParams(-1, -2))
        root.addView(TextView(this).apply {
            text = "오늘도 반짝반짝 행복한 하루!"
            textSize = 14f
            setTextColor(Color.rgb(130, 78, 111))
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, 16)
        }, LinearLayout.LayoutParams(-1, -2))
        root.addView(TextView(this).apply {
            text = java.text.SimpleDateFormat("M월 d일 E요일", java.util.Locale.KOREAN).format(java.util.Date())
            textSize = 16f
            setTextColor(deepPink)
            gravity = Gravity.CENTER
            background = rounded(Color.WHITE, 28f)
            setPadding(14, 12, 14, 12)
        }, LinearLayout.LayoutParams(-1, -2))

        search = EditText(this).apply {
            hint = "앱 이름 검색"
            textSize = 16f
            singleLine = true
            setTextColor(deepPink)
            background = rounded(Color.WHITE, 24f)
            setPadding(18, 8, 18, 8)
        }
        root.addView(search, LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, 14, 0, 4) })
        val scroller = ScrollView(this)
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 8, 0, 8) }
        scroller.addView(list)
        root.addView(scroller, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)

        search.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) { populate(s?.toString().orEmpty()) }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })
        populate("")
    }

    private fun rounded(color: Int, radius: Float) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = radius
        setStroke(1, Color.rgb(255, 195, 222))
    }

    private fun populate(query: String) {
        list.removeAllViews()
        val pm = packageManager
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val apps = pm.queryIntentActivities(intent, PackageManager.MATCH_ALL)
            .filter { it.activityInfo.packageName != packageName }
            .distinctBy { it.activityInfo.packageName }
            .filter { it.loadLabel(pm).toString().contains(query, ignoreCase = true) }
            .sortedBy { it.loadLabel(pm).toString().lowercase() }

        if (apps.isEmpty()) {
            list.addView(TextView(this).apply {
                text = if (query.isBlank()) "앱 목록을 불러오지 못했어요." else "검색 결과가 없어요."
                textSize = 16f
                gravity = Gravity.CENTER
                setPadding(8, 28, 8, 28)
                setTextColor(deepPink)
            })
        }
        apps.forEach { info ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                background = rounded(Color.WHITE, 20f)
                setPadding(12, 10, 12, 10)
            }
            row.addView(ImageView(this).apply { setImageDrawable(info.loadIcon(pm)) },
                LinearLayout.LayoutParams(42, 42))
            row.addView(TextView(this).apply {
                text = info.loadLabel(pm)
                textSize = 16f
                setTextColor(Color.rgb(92, 50, 77))
            }, LinearLayout.LayoutParams(0, -2, 1f).apply { setMargins(12, 0, 0, 0) })
            row.setOnClickListener {
                pm.getLaunchIntentForPackage(info.activityInfo.packageName)?.let { startActivity(it) }
            }
            list.addView(row, LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, 5, 0, 5) })
        }
    }
}
