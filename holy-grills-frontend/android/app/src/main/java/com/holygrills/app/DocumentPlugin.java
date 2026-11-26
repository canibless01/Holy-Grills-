package com.holygrills.app;

import android.app.Activity;
import android.content.Intent;
import android.util.Base64;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.OutputStream;

/** Android's Save As picker grants only the document selected by the user. */
@CapacitorPlugin(name = "HolyGrillsDocuments")
public class DocumentPlugin extends Plugin {
    @PluginMethod public void save(PluginCall call) {
        String data = call.getString("data", "");
        if (data.isEmpty() || data.length() > 28000000) { call.reject("Invalid document"); return; }
        String name = call.getString("name", "Holy-Grills.pdf").replaceAll("[^a-zA-Z0-9._-]", "_");
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType(call.getString("mime", "application/octet-stream"));
        intent.putExtra(Intent.EXTRA_TITLE, name);
        startActivityForResult(call, intent, "documentSelected");
    }
    @ActivityCallback private void documentSelected(PluginCall call, ActivityResult result) {
        if (call == null) return;
        JSObject response = new JSObject();
        if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null || result.getData().getData() == null) {
            response.put("cancelled", true); call.resolve(response); return;
        }
        try (OutputStream stream = getContext().getContentResolver().openOutputStream(result.getData().getData(), "w")) {
            if (stream == null) { call.reject("Document location is unavailable"); return; }
            stream.write(Base64.decode(call.getString("data", ""), Base64.DEFAULT));
            response.put("saved", true); call.resolve(response);
        } catch (Exception ignored) { call.reject("Document could not be saved"); }
    }
}
