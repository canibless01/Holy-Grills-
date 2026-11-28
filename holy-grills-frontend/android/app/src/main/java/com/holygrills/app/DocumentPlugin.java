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
import java.io.File;
import java.io.FileOutputStream;
import java.util.UUID;
import androidx.core.content.FileProvider;

/** Android's Save As picker grants only the document selected by the user. */
@CapacitorPlugin(name = "HolyGrillsDocuments")
public class DocumentPlugin extends Plugin {
    @PluginMethod public void prepareShare(PluginCall call) {
        String data = call.getString("data", ""), mime = call.getString("mime", "");
        if (data.isEmpty() || data.length() > 28000000 || !(mime.equals("image/png") || mime.equals("image/jpeg"))) { call.reject("Invalid share image"); return; }
        try {
            File directory = new File(getContext().getCacheDir(), "holy-grills-shares");
            if (!directory.exists() && !directory.mkdirs()) { call.reject("Share storage unavailable"); return; }
            File[] older = directory.listFiles();
            if (older != null) for (File file : older) if (file.lastModified() < System.currentTimeMillis() - 86400000L) file.delete();
            File image = new File(directory, UUID.randomUUID().toString() + (mime.equals("image/png") ? ".png" : ".jpg"));
            try (OutputStream stream = new FileOutputStream(image)) { stream.write(Base64.decode(data, Base64.DEFAULT)); }
            JSObject result = new JSObject();
            result.put("uri", FileProvider.getUriForFile(getContext(), getContext().getPackageName() + ".fileprovider", image).toString());
            call.resolve(result);
        } catch (Exception ignored) { call.reject("Share image could not be prepared"); }
    }
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
