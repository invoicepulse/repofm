/**
 * Validates that a string is a valid public GitHub repository URL.
 * Expected format: https://github.com/{owner}/{repo}
 */
export function isValidGitHubUrl(url: string): boolean {
  return /^https:\/\/github\.com\/[^/]+\/[^/]+$/.test(url);
}
