package com.holygrills.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** JWTs are AES-GCM encrypted with a non-exportable Android Keystore key. */
@CapacitorPlugin(name = "HolyGrillsSecureSession")
public class SecureSessionPlugin extends Plugin {
    private static final String ALIAS = "holygrills.session.v1";
    private SharedPreferences preferences() {
        return getContext().getSharedPreferences("holygrills_secure_session", Context.MODE_PRIVATE);
    }
    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (store.containsAlias(ALIAS)) return ((KeyStore.SecretKeyEntry) store.getEntry(ALIAS, null)).getSecretKey();
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true).build());
        return generator.generateKey();
    }
    @PluginMethod public synchronized void load(PluginCall call) {
        try {
            String ciphertext = preferences().getString("ciphertext", null);
            if (ciphertext == null) { call.resolve(new JSObject()); return; }
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            byte[] iv = Base64.decode(preferences().getString("iv", ""), Base64.NO_WRAP);
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
            byte[] plaintext = cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP));
            call.resolve(new JSObject(new String(plaintext, StandardCharsets.UTF_8)));
        } catch (Exception ignored) { call.reject("Secure session could not be opened", "SECURE_SESSION_UNAVAILABLE"); }
    }
    @PluginMethod public synchronized void save(PluginCall call) {
        try {
            String access = call.getString("access", ""), refresh = call.getString("refresh", "");
            if (access.length() > 32768 || refresh.length() > 32768) { call.reject("Invalid session"); return; }
            JSObject value = new JSObject(); value.put("access", access); value.put("refresh", refresh);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
            String ciphertext = Base64.encodeToString(cipher.doFinal(value.toString().getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
            boolean saved = preferences().edit().putString("ciphertext", ciphertext)
                .putString("iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)).commit();
            if (!saved) { call.reject("Secure session could not be saved"); return; }
            call.resolve();
        } catch (Exception ignored) { call.reject("Secure session could not be saved", "SECURE_SESSION_UNAVAILABLE"); }
    }
    @PluginMethod public synchronized void clear(PluginCall call) {
        try {
            if (!preferences().edit().clear().commit()) { call.reject("Secure session could not be cleared"); return; }
            KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null); store.deleteEntry(ALIAS);
            call.resolve();
        } catch (Exception ignored) { call.reject("Secure session could not be cleared", "SECURE_SESSION_UNAVAILABLE"); }
    }
}
