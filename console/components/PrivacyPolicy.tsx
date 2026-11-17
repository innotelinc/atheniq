import { brandOf } from "@/lib/branding";
import { LEGAL_EMAIL } from "@/lib/legal";
import { getDb } from "@/lib/store";

/**
 * The privacy policy, shared so the website and the console's public page
 * (/privacy) publish the same words: the App Store needs one stable URL, and a
 * second copy of a legal text is how two versions of it start.
 */
export function PrivacyPolicy() {
  const db = getDb();
  const brand = brandOf(db.settings);

  return (
    <div className="prose">
      <p>
        {brand.siteName} runs courses, issues credentials, and keeps the records a registrar needs. This policy covers
        the {brand.siteName} iOS app and {brand.domain}. Effective 17 November 2026.
      </p>

      <h2>What we store</h2>
      <ul>
        <li>
          <strong>Your account.</strong> Name, email address, and a password hash or, for staff, the identity your
          school sign-in provider returns. Staff accounts also carry a two-factor secret and recovery codes.
        </li>
        <li>
          <strong>Your coursework.</strong> Which courses you enrolled in, which lessons you opened, your progress, and
          the certificates or credentials issued to you.
        </li>
        <li>
          <strong>Payments.</strong> When a course has a price, we store the payment reference, the amount and the
          registrar&apos;s decision. We never see or store card numbers: payment happens outside the app.
        </li>
        <li>
          <strong>Notifications.</strong> If you allow them, the app sends us a device push token so a certificate or a
          payment decision can reach you. The token identifies the installation, not you.
        </li>
        <li>
          <strong>Downloads.</strong> Lessons you download for offline study are kept in the app&apos;s own storage on
          your device and removed when you delete the app.
        </li>
        <li>
          <strong>Security records.</strong> Sign-in attempts, device and IP information, and the activity trail a
          registrar can review.
        </li>
      </ul>

      <h2>Why we use it</h2>
      <p>
        To run your courses, track progress, issue and verify credentials, confirm payments with the registrar, send the
        notifications you asked for, and keep the account secure. We do not run advertising, and we do not track you
        across other apps or websites.
      </p>

      <h2>Who processes it</h2>
      <p>
        Course and account data live on servers operated for {brand.siteName}. Push notifications pass through
        Apple&apos;s push service and Expo&apos;s notification service, which receive the device token and the
        notification text. Identity for staff sign-in is handled by the school&apos;s single sign-on provider. We do not
        sell personal data.
      </p>

      <h2>How long we keep it</h2>
      <p>
        Account and coursework records are kept while your account exists and afterwards for as long as the school must
        keep academic and credential records. Security logs are kept for a limited period. Offline downloads stay on
        your device until you remove them.
      </p>

      <h2>Your choices</h2>
      <p>
        You can turn notifications off in iOS Settings, sign out at any time, and ask us to correct or delete your
        account by writing to <a href={`mailto:${LEGAL_EMAIL}`}>{LEGAL_EMAIL}</a>. Deleting an account removes your profile and
        enrollments; issued credentials may be retained where the school must be able to verify them.
      </p>

      <h2>Children</h2>
      <p>
        The app is intended for students of the school and is not directed at children under 13. If a course enrolls
        younger students, the school obtains consent as its own policies require.
      </p>

      <h2>Changes and contact</h2>
      <p>
        If this policy changes, the date above changes with it. Questions go to <a href={`mailto:${LEGAL_EMAIL}`}>{LEGAL_EMAIL}</a>.
      </p>
    </div>
  );
}
